########################################################################
# amara/xslt/processor.py
"""
XSLT processing engine
"""
import os, sys, operator, cStringIO, warnings
from xml.dom import Node
from gettext import gettext as _

DEFAULT_ENCODING = 'UTF-8'
#from amara import DEFAULT_ENCODING
from amara import ReaderError, domlette
from amara.lib import iri, inputsource
from amara.xpath import XPathError
from amara.xslt import XsltError
from amara.xslt import xsltcontext, proxywriter
from amara.xslt.reader import stylesheet_reader

# For builtin extension elements/functions
#from amara.xslt import exslt
#from amara.xslt.extensions import builtins


# Media types that signal that an xml-stylesheet PI points to an XSLT
# document, when the PI contains a type pseudo-attribute.
#
# Note: RFC 3023 suggests application/xslt+xml, and says the +xml
# suffix is not required (but is a SHOULD). If you want to use the
# 'text/xsl' convention, do Processor.XSLT_IMT.append('text/xsl')
# after import, but before instantiating Processor.Processor.
#
XSLT_IMT = ['application/xslt+xml', 'application/xslt',
            'text/xml', 'application/xml']


# for xsl:message output
MESSAGE_TEMPLATE = _('STYLESHEET MESSAGE:\n%s\nEND STYLESHEET MESSAGE\n')

class processor(object):
    """
    An XSLT processing engine (4XSLT).

    Typical usage:

    from Ft.Lib.Uri import OsPathToUri
    from Ft.Xml import InputSource
    from Ft.Xml.Xslt import Processor
    # this is just one of several ways to create InputSources
    styuri = OsPathToUri('/absolute/path/to/stylesheet.xslt')
    srcuri = OsPathToUri('/absolute/path/to/doc.xml')
    STY = InputSource.DefaultFactory.fromUri(styuri)
    SRC = InputSource.DefaultFactory.fromUri(srcuri)
    proc = Processor.Processor()
    proc.appendStylesheet(STY)
    result = proc.run(SRC)

    See the run() and runNode() methods for additional runtime options.

        The ignore_pis flag, if true, will cause xml-stylesheet
        processing instructions in the source document to be ignored.

    Important instance attributes:

      .extensionParams: a dictionary that allows one to attach
        additional metadata to a processor instance. We use this
        to make invocation-specific data like HTTP query args and
        logfile handles available to XSLT extension functions & elements
        when invoking the processor via the repository's HTTP server.

      .mediaPref: the preferred/target media, for the purpose of
        picking from multiple xml-stylesheet processing instructions.
        Defaults to None. If set to a string, xml-stylesheet PIs
        without that string in their 'media' pseudo-attribute will be
        ignored.

      .message_template: format string for `xsl:message` output.

      .transform: the complete transformation tree.

    """
    # defaults for ExtendedProcessingElements.ExtendedProcessor
    _4xslt_debug = False
    _4xslt_profile = False
    _4xslt_trace = False

    _suppress_messages = False

    # has the "built-in template invoked with params" warning been issued?
    _builtInWarningGiven = False

    def __init__(self, ignore_pis=False, content_types=None,
                 media_descriptors=None, extension_parameters=None,
                 message_template=None):
        self.ignore_pis = ignore_pis
        if content_types is None:
            content_types = set(XSLT_IMT)
        self.content_types = content_types
        # Although nt in the DTD, the prose for HTML LINK element states that
        # the default value for the media attribute is "screen".
        if media_descriptors is None:
            media_descriptors = set(['screen'])
        self.media_descriptors = media_descriptors
        if extension_parameters is None:
            extension_parameters = {}
        self.extension_parameters = extension_parameters
        if message_template is None:
            message_template = MESSAGE_TEMPLATE
        self.message_template = message_template
        self.transform = None

        self._extfunctions = {}  #Cache ext functions to give to the context
        self._extelements = {}
        #self._extelements.update(exslt.ExtElements)
        #self._extelements.update(builtins.ExtElements)
        self._reader = stylesheet_reader()
        return

    def getStripElements(self):
        if self.transform:
            return self.transform.space_rules
        else:
            return ()

    def registerExtensionModules(self, modules):
        """
        Registers a list of Python modules that have public ExtFunctions
        and/or ExtElements dictionaries.

        In a Python module that contains extension implementations,
        define a dictionary named ExtFunctions that, for each extension
        function or element, maps a (namespace-URI, xpath-function-name)
        tuple to a direct reference to the Python function that
        implements the extension. To make the function available to the
        Processor, call this method, passing in ['your.module.name'].

        See Ft.Xml.Xslt.Exslt.*, Ft.Xml.Xslt.BuiltInExtFunctions and
        BuiltInExtElements for working examples of extension modules.
        """
        for module in modules:
            if module:
                module = __import__(module, {}, {}, ['ExtFunctions'])
                if hasattr(module, 'ExtFunctions'):
                    self._extfunctions.update(mod.ExtFunctions)
                if hasattr(module, 'ExtElements'):
                    elements = module.ExtElements
                    self._extelements.update(elements)
                    self._reader.addExtensionElementMapping(elements)
        return

    def registerExtensionFunction(self, namespace, localName, function):
        """
        Register a single extension function.

        For example, implement your own extension function as a Python
        function that takes an Ft.Xml.XPath.Context.Context instance as
        its first argument. Then, to make the function available to the
        Processor, call this method, passing in the namespace URI and
        local name of the function, and a direct reference to the Python
        function that implements the extension.

        See also registerExtensionModules().
        """
        self._extfunctions[namespace, localName] = function
        return

    def registerExtensionElement(self, namespace, localName, klass):
        """
        Register a single extension element.

        For example, implement your own extension element as a subclass
        of Ft.Xml.Xslt.xsltelement. To make the element available to the
        Processor, call this method, passing in the namespace URI and
        local name of the element, and a direct reference to the class
        that implements the extension.

        See also registerExtensionModules().
        """
        self._extelements[namespace, localName] = klass
        mapping = { (namespace, localName) : klass }
        self._reader.addExtensionElementMapping(mapping)
        return

    def append_transform(self, source, uri=None):
        """
        Add an XSL transformation document to the processor.

        uri - optional override document URI.

        This method establishes the transformation that the processor will use
        to transform a source tree into a result tree.  If a transform has
        already been appended, then this method is equivalent to having, in an
        outer "shell" document, an `xsl:import` for the most recently added
        transform followed by an `xsl:import` for the document accessible via
        the given `transform`.
        """
        if isinstance(source, Node):
            document = source.ownerDocument or source
            if not uri:
                try:
                    uri = document.documentURI
                except AttributeError:
                    try:
                        uri = document.baseURI
                    except AttributeError:
                        raise ValueError('base-uri required for %s' %
                                         document)
            self._documents[uri] = document
            self.transform = self._reader.parse(document)
        else:
            if not isinstance(source, inputsource):
                source = inputsource(source, uri)
            self.transform = self._reader.parse(source)
        return

    def run(self, source, topLevelParams=None, writer=None, output=None):
        """
        Transform a source document as given via an InputSource.

        Assumes that either the Processor instance has already had
        stylesheets appended (via appendStylesheet(), for example), or
        the source document contains xml-stylesheet processing
        instructions that are not being ignored.

        The topLevelParams argument is an optional dictionary of
        stylesheet parameters, the keys of which may be given as
        strings if they have no namespace, or as (uri, localname)
        tuples otherwise.

        The optional writer argument is a SAX-like event handler that
        is an Ft.Xml.Xslt.NullWriter subclass. The default writer is
        either an Ft.Xml.Xslt.XmlWriter, HtmlWriter or PlainTextWriter,
        depending on the stylesheet(s).

        The optional outputStream argument is a Python file-like object
        to be used as the destination for the writer's output.
        """
        #Update the strip elements
        #Assume that the ones from XSLT have higher priority
        ns = self.getStripElements()
        ignorePis = False
        try:
            document = domlette.parse(source)
        except ReaderError, e:
            raise XsltError(XsltError.SOURCE_PARSE_ERROR,
                            source.uri or '<Python string>', e)
        if not ignorePis and self.__checkStylesheetPis(document, source):
            #Do it again with updates WS strip lists

            #NOTE:  There is a case where this will produce the wrong results.  If, there were
            #previous stylesheets that defined removing white space, then the
            #processing instruction referenced a stylesheet that overrode some of these
            #whitespace processing rules, the original trimmed space will be lost

            #Regardless, we need to remove any new whitespace defined in the PI
            self._stripElements(document)

        return self._run(document, topLevelParams, writer, output)

    def runNode(self, node, sourceUri=None,
                topLevelParams=None, writer=None, outputStream=None,
                preserveSrc=0, docInputSource=None):
        """
        Transform a source document as given via a Domlette document
        node.

        Use Ft.Xml.Domlette.ConvertDocument() to create a Domlette
        from some other type of DOM.

        Assumes that either the Processor instance has already had
        stylesheets appended (via appendStylesheet(), for example), or
        the source document contains xml-stylesheet processing
        instructions that are not being ignored.

        sourceUri - The absolute URI of the document
        entity that the node represents, and should be explicitly
        provided, even if it is available from the node itself.

        ignorePis - (flag) If set, will cause xml-stylesheet
        processing instructions in the source document to be ignored.

        topLevelParams - optional dictionary of
        stylesheet parameters, the keys of which may be given as
        strings if they have no namespace, or as (uri, localname)
        tuples otherwise.

        writer - optional SAX-like event handler that
        is an Ft.Xml.Xslt.NullWriter subclass. The default writer is
        either an Ft.Xml.Xslt.XmlWriter, HtmlWriter or PlainTextWriter,
        depending on the stylesheet(s).

        outputStream - optional Python file-like object
        to be used as the destination for the writer's output.

        preserveSrc - (flag) If set signals that the source DOM should not be
        mutated, as would normally happen when honoring XSLT whitespace
        stripping requirements. Setting preserveSrc results in the
        creation of a copy of the source DOM.

        isrc - optional input source used strictly for further resolution
        relative the given DOM
        """

        if node.nodeType != Node.DOCUMENT_NODE:
            raise ValueError(MessageSource.g_errorMessages[
                             XsltError.CANNOT_TRANSFORM_FRAGMENT])

        if hasattr(node, 'baseURI'):
            node_baseUri = node.baseURI
        elif hasattr(node, 'refUri'):
            node_baseUri = node.refUri
        else:
            node_baseUri = None

        #A base URI must be absolute, but DOM L3 Load & Save allows
        # implementation-dependent behavior if the URI is actually
        # relative, empty or missing. We'll generate a URN for the
        # InputSource's benefit if the base URI is empty/missing.
        # Relative URIs can pass through; the resolvers will handle
        # them appropriately (we hope).
        if not sourceUri:
            sourceUri = node_baseUri or Uri.BASIC_RESOLVER.generate()

        if preserveSrc:
            #preserve the node's baseURI so our DOM is a true copy
            newDoc = self._domimp.createRootNode(node_baseUri)
            for child in node.childNodes:
                new_node = newDoc.importNode(child,1)
                newDoc.appendChild(new_node)
                node = newDoc

        self._stripElements(node)

        if not docInputSource:
            #Create a dummy iSrc
            docInputSource = inputsource.input_source(
                None, sourceUri, processIncludes=1,
                stripElements=self.getStripElements(),
                factory=self.inputSourceFactory)

        if not ignorePis and self.__checkStylesheetPis(node, docInputSource):
            #Do it again with updated WS strip lists

            #NOTE:  There is a case where this will produce the wrong results.  If, there were
            #previous stylesheets that defined removing white space, then the
            #processing instruction referenced a stylesheet that overrode some of these
            #whitespace processing rules, the original trimmed space will be lost

            #Regardless, we need to remove any new whitespace defined in the PI
            self._stripElements(node)


        return self._run(node,
                            ignorePis=ignorePis,
                            topLevelParams=topLevelParams,
                            writer=writer,
                            outputStream=outputStream)

    def __cmp_stys(self, a, b):
        """
        Internal function to assist in sorting xml-stylesheet
        processing instructions. See __checkStylesheetPis().
        """
        # sort by priority (natural order)
        return cmp(a[0], b[0])
        ##
        ## For future reference, to support more advanced
        ## preferences, such as having an ordered list of
        ## preferred target media values rather than just one,
        ## and using the Internet media type list in a similar
        ## fashion, we can sort on multiple pseudo-attrs like
        ## this:
        ##
        ## sort by priority (natural order)
        #if cmp(a[0], b[0]):
        #    return cmp(a[0], b[0])
        ## then media (natural order)
        #elif cmp(a[1], b[1]):
        #    return cmp(a[1], b[1])
        ## then type (XSLT_IMT order)
        #else:
        #    for imt in XSLT_IMT:
        #        if a[2] == imt:
        #            return b[2] != imt
        #        else:
        #            return -(b[2] == imt)

    def __checkStylesheetPis(self, node, inputSource):
        """
        Looks for xml-stylesheet processing instructions that are
        children of the given node's root node, and calls
        appendStylesheet() for each one, unless it does not have an
        RFC 3023 compliant 'type' pseudo-attribute or does not have
        a 'media' pseudo-attribute that matches the preferred media
        type that was set as Processor.mediaPref. Uses the given
        InputSource to resolve the 'href' pseudo-attribute. If the
        instruction has an alternate="yes" pseudo-attribute, it is
        treated as a candidate for the first stylesheet only.
        """
        # relevant links:
        # http://www.w3.org/TR/xml-stylesheet/
        # http://lists.fourthought.com/pipermail/4suite/2001-January/001283.html
        # http://lists.fourthought.com/pipermail/4suite/2003-February/005088.html
        # http://lists.fourthought.com/pipermail/4suite/2003-February/005108.html
        #
        # The xml-stylsheet spec defers to HTML 4.0's LINK element
        # for semantics. It is not clear in HTML how the user-agent
        # should interpret multiple LINK elements with rel="stylesheet"
        # and without alternate="yes". In XSLT processing, we, like
        # Saxon, choose to treat such subsequent non-alternates as
        # imports (i.e. each non-alternate stylesheet is imported by
        # the previous one).
        #
        # Given that alternates can appear before or after the
        # non-alternate, there's no way to know whether they apply
        # to the preceding or following non-alternate. So we choose
        # to just treat alternates as only applying to the selection
        # of the first stylesheet.
        #
        # Also, the absence of processing guidelines means we can't
        # know whether to treat the absence of a 'media' pseudo-attr
        # as implying that this is a default stylesheet (e.g. when the
        # preferred media is "foo" and there is no "foo", you use
        # this stylesheet), or whether to treat it as only being the
        # appropriate stylesheet when no media preference is given to
        # the processor.
        #
        # Furthermore, if more than one candidate for the first
        # stylesheet is a match on the 'media' preference (or lack
        # thereof), it's not clear what to do. Do we give preference
        # to the one with a 'type' that is considered more favorable
        # due to its position in the XSLT_IMT list? Do we just use the
        # first one? The last one? For now, if there's one that does
        # not have alternate="yes", we use that one; otherwise we use
        # the first one. Thus, given
        #  <?xml-stylesheet type="application/xslt+xml" href="sty0"?>
        #  <?xml-stylesheet type="application/xslt+xml" href="sty1"
        #    alternate="yes"?>
        # sty0 is used, even if the PIs are swapped; whereas if the
        # only choices are
        #  <?xml-stylesheet type="application/xslt+xml" href="sty1"
        #    alternate="yes"?>
        #  <?xml-stylesheet type="application/xslt+xml" href="sty2"
        #    alternate="yes"?>
        # then sty1 is used because it comes first.
        root = node.rootNode
        c = 1 # count of alternates, +1
        found_nonalt = 0
        stys = []
        for child in root.childNodes:
            # only look at prolog, not anything that comes after it
            if child.nodeType == Node.ELEMENT_NODE:
                break
            # build dict of pseudo-attrs for the xml-stylesheet PIs
            if child.nodeType == Node.PROCESSING_INSTRUCTION_NODE:
                if child.target == 'xml-stylesheet':
                    data = child.data.split()
                    pseudo_attrs = {}
                    for d in data:
                        seg = d.split('=')
                        if len(seg) == 2:
                            pseudo_attrs[seg[0]] = seg[1][1:-1]

                    # PI must have both href, type pseudo-attributes;
                    # type pseudo-attr must match valid XSLT types;
                    # media pseudo-attr must match preferred media
                    # (which can be None)
                    if 'href' in pseudo_attrs and 'type' in pseudo_attrs:
                        href = pseudo_attrs['href']
                        imt = pseudo_attrs['type']
                        media = pseudo_attrs.get('media') # defaults to None
                        if media in self.media_descriptors and imt in XSLT_IMT:
                            if pseudo_attrs.has_key('alternate') and \
                                pseudo_attrs['alternate'] == 'yes':
                                stys.append((1, media, imt,
                                             pseudo_attrs['href']))
                            elif found_nonalt:
                                c += 1
                                stys.append((c, media, imt,
                                             pseudo_attrs['href']))
                            else:
                                stys.append((0, media, imt,
                                             pseudo_attrs['href']))
                                found_nonalt = 1

        stys.sort(self.__cmp_stys)

        # Assume stylesheets for irrelevant media and disallowed IMTs
        # are filtered out. Assume stylesheets are in ascending order
        # by level. Now just use first stylesheet at each level, but
        # treat levels 0 and 1 the same. Meaning of the levels:
        #  level 0 is first without alternate="yes"
        #  level 1 is all with alternate="yes"
        #  levels 2 and up are the others without alternate="yes"
        hrefs = []
        last_level = -1
        #print "stys=",repr(stys)
        for sty in stys:
            level = sty[0]
            if level == 1 and last_level == 0:
                # we want to ignore level 1s if we had a level 0
                last_level = 1
            if level == last_level:
                # proceed to next level (effectively, we only use
                # the first stylesheet at each level)
                continue
            last_level = level
            hrefs.append(sty[3])

        if hrefs:
            for href in hrefs:
                # Resolve the PI with the InputSource for the document
                # containing the PI, so relative hrefs work correctly
                new_source = inputSource.resolve(href,
                                                 hint='xml-stylesheet PI')
                self.appendStylesheet(new_source)

        # Return true if any xml-stylesheet PIs were processed
        # (i.e., the stylesheets they reference are going to be used)
        return not not hrefs

    def _run(self, node, ignorePis=0, topLevelParams=None, writer=None,
             outputStream=None):
        """
        Warning: do not call this method directly unless you know what
        you're doing.  If unsure, you probably want the runNode method.

        Runs the stylesheet processor against the given XML DOM node with the
        stylesheets that have been registered. It does not mutate the source.
        If writer is given, it is used in place of the default output method
        decisions for choosing the proper writer.
        """
        #QUESTION: What about ws stripping?
        #ANSWER: Whitespace stripping happens only in the run*() interfaces.
        #  This method is use-at-your-own-risk. The XSLT conformance of the
        #  source is maintained by the caller. This exists as a performance
        #  hook.
        topLevelParams = topLevelParams or {}

        self.attributeSets = {}
        self.keys = {}

        #See f:chain-to extension element
        self.chainTo = None
        self.chainParams = None

        if not self.transform:
            raise XsltError(XsltError.NO_STYLESHEET)
        self.outputParams = self.transform.output_parameters

        # Use an internal stream to gather the output only if the caller
        # didn't supply other means of retrieving it.
        internalStream = writer is None and outputStream is None

        if not writer:
            # Use OutputHandler to determine the real writer to use.
            stream = outputStream or cStringIO.StringIO()
            writer = proxywriter.proxywriter(self.outputParams, stream)
        self.writers = [writer]

        # Initialize any stylesheet parameters
        initial_variables = topLevelParams.copy()
        for name in topLevelParams:
            if name not in self.transform.parameters:
                del initial_variables[name]

        # Prepare the stylesheet for processing
        context = xsltcontext.xsltcontext(node,
                                          variables=initial_variables,
                                          processor=self,
                                          extfunctions=self._extfunctions)
        context.add_document(node, node.baseURI)
        self.transform.root.prime(context)

        # Process the document
        context.start_document()
        try:
            self.transform.apply_templates(context, [node])
        except XPathError, e:
            instruction = context.currentInstruction
            strerror = str(e)
            e.message = MessageSource.EXPRESSION_POSITION_INFO % (
                instruction.baseUri, instruction.lineNumber,
                instruction.columnNumber, instruction.nodeName, strerror)
            raise
        except XsltError:
            raise
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            raise
            import traceback
            sio = cStringIO.StringIO()
            sio.write("Lower-level traceback:\n")
            traceback.print_exc(None, sio)
            instruction = context.currentInstruction
            strerror = sio.getvalue()
            raise RuntimeError(MessageSource.EXPRESSION_POSITION_INFO % (
                instruction.baseUri, instruction.lineNumber,
                instruction.columnNumber, instruction.nodeName, strerror))
        context.end_document()

        # Perform cleanup
        self.transform.root.teardown()

        if internalStream:
            # Get the result from our cStringIO 'stream'.
            result = stream.getvalue()
        else:
            # It is the callers responsibility to get the result
            result = u""
        return result

    def applyTemplates(self, context, params=None):
        """
        Intended to be used by XSLT instruction implementations only.

        Implements the xsl:apply-templates instruction by attempting to
        let the stylesheet apply its own template for the given context.
        If the stylesheet does not have a matching template, the
        built-in templates are invoked.

        context is an XsltContext instance. params is a dictionary of
        parameters being passed in, defaulting to None.
        """
        if params is None:
            params = {}
        if not self.stylesheet.applyTemplates(context, self, params):
            # No matching templates found, use builtin templates
            if params and not self._builtInWarningGiven:
                self.warning(MessageSource.BUILTIN_TEMPLATE_WITH_PARAMS)
                self._builtInWarningGiven = 1
            if context.node.nodeType == Node.TEXT_NODE:
                self.writers[-1].text(context.node.data)
            elif context.node.nodeType in [Node.ELEMENT_NODE, Node.DOCUMENT_NODE]:
                state = context.copy()
                node_set = context.node.childNodes
                size = len(node_set)
                pos = 1
                for node in node_set:
                    context.node, context.position, context.size = \
                                  node, pos, size
                    self.applyTemplates(context)
                    pos += 1
                context.set(state)
            elif context.node.nodeType == Node.ATTRIBUTE_NODE:
                self.writers[-1].text(context.node.value)
        return

    def message_control(self, suppress):
        """
        Controls whether the processor emits warnings and xsl:message
        messages. Call with suppress=1 to suppress such output.
        """
        self._suppress_messages = not not suppress
        return

    def message(self, message):
        """
        Intended to be used by XSLT instruction implementations only.

        Used by xsl:message to emit a message to sys.stderr, unless such
        messages are suppressed (see messageControl()). Uses the
        msgPrefix & msgSuffix instance attributes.
        """
        message = self.message_template % (msg,)
        if not self._suppress_messages:
            sys.stderr.write(message)
            sys.stderr.flush()
        return

    def warning(self, message):
        """
        Emits a warning via Python's warnings framework, unless warnings
        are suppressed (see messageControl()).

        Used, for example, to announce that built-in templates are being
        invoked with params.
        """
        if not self._suppress_messages:
            # Using level=2 to show the stack where the warning occured.
            warnings.warn(message, stacklevel=2)
        return

    def addHandler(self, outputParams, stream):
        """
        Intended to be used by XSLT instruction implementations only.

        Sets up the processor to start processing subsequently
        generated content with an output writer wrapper that first
        determines which XSLT output method is going to be used (i.e.,
        by looking at the output parameters or waiting to see if an
        'html' element is the first new node generated), then replaces
        itself with the appropriate writer instance.

        outputParams is an Ft.Xml.Xslt.OutputParameters instance.

        stream will be passed on to the constructor of the real writer.
        """
        handler = OutputHandler.OutputHandler(outputParams, stream)
        self.writers.append(handler)
        handler.startDocument()
        return

    def removeHandler(self):
        """
        Intended to be used by XSLT instruction implementations only.

        Deletes the most recently added output writer.
        """
        self.writers[-1].endDocument()
        del self.writers[-1]
        return

    def pushResultTree(self, baseUri, implementation=None):
        """
        Intended to be used by XSLT instruction implementations only.

        Sets up the processor to start processing subsequently
        generated content with a new output writer that produces
        a separate document. The new document will have the given
        baseUri as its URI. This is used to generate result tree
        fragments.

        Allows specifying an alternative DOM implementation for the
        creation of the new document.
        """
        writer = RtfWriter.RtfWriter(self.outputParams, baseUri)
        self.writers.append(writer)
        return writer

    def pushResultString(self):
        """
        Intended to be used by XSLT instruction implementations only.

        Sets up the processor to start processing subsequently
        generated content with an output writer that buffers the text
        from text events and keeps track of whether non-text events
        occurred. This is used by the implementations of XSLT
        instructions such as xsl:attribute.
        """
        writer = StringWriter.StringWriter(self.outputParams)
        self.writers.append(writer)
        return

    def pushResult(self, handler=None):
        """
        Intended to be used by XSLT instruction implementations only.

        Sets up the processor to start processing subsequently
        generated content with a new output writer (the given handler
        of SAX-like output events).
        """
        if handler is None:
            warnings.warn("Use pushResultTree(uri) to create RTFs",
                          DeprecationWarning, stacklevel=2)
            handler = RtfWriter.RtfWriter(self.outputParams,
                                          self.stylesheet.baseUri)
        self.writers.append(handler)
        handler.startDocument()
        return

    def popResult(self):
        """
        Intended to be used by XSLT instruction implementations only.

        Ends temporary output writing that was started with
        pushResultString(), pushResultTree(), or pushResult(), and
        returns the result.
        """
        handler = self.writers[-1]
        del self.writers[-1]
        handler.endDocument()
        return handler.getResult()

    def writer(self):
        """
        Intended to be used by XSLT instruction implementations only.

        Returns the current output writer.
        """
        return self.writers[-1]
    writer = property(writer)

    def _strip_elements(self, node):
        stripElements = self.getStripElements()
        if stripElements:
            StripElements.StripElements(node, stripElements)
        return

    def reset(self):
        """
        Returns the processor to a state where it can be used to do a
        new transformation with a new stylesheet. Deletes the current
        stylesheet tree, and may do other cleanup.
        """
        self.stylesheet = None
        self.getStylesheetReader().reset()
        return
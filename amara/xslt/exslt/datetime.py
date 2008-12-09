########################################################################
# amara/xslt/exslt/datetime.py
"""
EXSLT - Dates an Times (http://www.exslt.org/date/index.html)
"""
import calendar

from amara.xpath import datatypes

EXSL_DATE_TIME_NS = 'http://exslt.org/dates-and-times'

## EXSLT Core Functions ##

def date_time_function(context):
    """
    The `date:date-time` function returns the current local date/time as an
    ISO 8601 formatted date/time string, with a time zone.

    Implements version 1.
    """
    return datatypes.string(_datetime.now())


def date_function(context, date=None):
    """
    The date:date function returns the date portion of the dateTime
    argument if present, or of the current local date/time. The
    argument can be given in xs:dateTime or xs:date format.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, date, ('dateTime', 'date'))
    except ValueError:
        return datatypes.EMPTY_STRING
    return datatypes.string(u'%-.4d-%02d-%02d%s' % (datetime.year,
                                                    datetime.month,
                                                    datetime.day,
                                                    datetime.timezone or ''))


def time_function(context, time=None):
    """
    The date:time function returns the time portion of the dateTime
    argument if present, or of the current local date/time. The
    argument can be given in xs:dateTime or xs:time format.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, time, ('dateTime', 'time'))
    except ValueError:
        return datatypes.EMPTY_STRING
    return datatypes.string(u'%02d:%02d:%02.12g%s' % (datetime.hour,
                                                      datetime.minute,
                                                      datetime.second,
                                                      datetime.timezone or ''))


def year_function(context, date=None):
    """
    The date:year function returns the year portion of the
    dateTime supplied, or of the current year, as an integer.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, date, ('dateTime', 'date', 'gYearMonth',
                                           'gYear'))
    except ValueError:
        return datatypes.NOT_A_NUMBER
    return datatypes.number(datetime.year)


def leap_year_function(context, date=None):
    """
    The date:leap-year function returns true if the year argument
    (defaults to current year) is a leap year, false otherwise.

    Implements version 1.
    """
    try:
        datetime = _coerce(context, date, ('dateTime', 'date', 'gYearMonth',
                                           'gYear'))
    except ValueError:
        return datatypes.NOT_A_NUMBER
    return datatypes.TRUE if _is_leap(datetime.year) else datatypes.FALSE


def month_in_year_function(context, date=None):
    """
    The date:month-in-year function returns the month portion of
    the dateTime argument (defaults to current month) as an integer.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, date, ('dateTime', 'date', 'gYearMonth',
                                           'gMonthDay', 'gMonth'))
    except ValueError:
        return datatypes.NOT_A_NUMBER
    return datatypes.number(datetime.month)


def month_name_function(context, date=None):
    """
    The date:month-name function returns the full English name
    of the month portion of a date.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, date, ('dateTime', 'date', 'gYearMonth',
                                           'gMonthDay', 'gMonth'))
    except ValueError:
        return datatypes.EMPTY_STRING
    return datatypes.string(
        (u'', u'January', u'February', u'March', u'April', u'May', u'June',
         u'July', u'August', u'September', u'October', u'November',
         u'December')[datetime.month])


def month_abbreviation_function(context, date=None):
    """
    The date:month-abbreviation function returns the abbreviation
    of the month of a date.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, date, ('dateTime', 'date', 'gYearMonth',
                                           'gMonthDay', 'gMonth'))
    except ValueError:
        return datatypes.EMPTY_STRING
    return datatypes.string(
        (u'', u'Jan', u'Feb', u'Mar', u'Apr', u'May', u'Jun', u'Jul', u'Aug',
         u'Sep', u'Oct', u'Nov', u'Dec')[datetime.month])


def week_in_year_function(context, date=None):
    """
    The date:week-in-year function returns a number representing
    the week of the year a date is in.

    Implements version 3.
    """
    # Notes:
    #  - ISO 8601 specifies that Week 01 of the year is the week containing
    #    the first Thursday;
    try:
        datetime = _coerce(context, date, ('dateTime', 'date'))
    except ValueError:
        return datatypes.NOT_A_NUMBER

    year, month, day = datetime.year, datetime.month, datetime.day

    # Find Jan 1 weekday for Y
    # _dayOfWeek returns 0=Sun, we need Mon=0
    day_of_week_0101 = (_day_of_week(year, 1, 1) + 6) % 7

    # Find weekday for Y M D
    day_number = _day_in_year(year, month, day)
    day_of_week = (day_number + day_of_week_0101 - 1) % 7

    # Find if Y M D falls in year Y-1, week 52 or 53
    #  (i.e., the first 3 days of the year and DOW is Fri, Sat or Sun)
    if day_of_week_0101 > 3 and day_number <= (7 - day_of_week_0101):
        week = 52 + (day_of_week_0101 == (4 + _is_leap(year - 1)))
    # Find if Y M D falls in Y+1, week 1
    #  (i.e., the last 3 days of the year and DOW is Mon, Tue, or Wed)
    elif (365 + _is_leap(year) - day_number) < (3 - day_of_week):
        week = 1
    else:
        week = (day_number + (6 - day_of_week) + day_of_week_0101) / 7
        if day_of_week_0101 > 3:
            week -= 1
    return datatypes.number(week)


def day_in_year_function(context, date=None):
    """
    The date:day-in-year function returns a number representing
    the position of a date in the year.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, date, ('dateTime', 'date'))
    except ValueError:
        return datatypes.NOT_A_NUMBER
    return datatypes.number(_day_in_year(datetime.year,
                                         datetime.month,
                                         datetime.day))


def day_in_month_function(context, date=None):
    """
    The date:day-in-month function returns the numerical date, i.e.
    27 for the 27th of March.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, date, ('dateTime', 'date', 'gMonthDay',
                                           'gDay'))
    except ValueError:
        return datatypes.NOT_A_NUMBER
    return datatypes.number(datetime.day)


def day_of_week_in_month_function(context, date=None):
    """
    The date:day-of-week-in-month function returns the day-of-the-week
    in a month of a date as a number (e.g. 3 for the 3rd Tuesday in May).

    Implements version 2.
    """
    try:
        datetime = _coerce(context, date, ('dateTime', 'date'))
    except ValueError:
        return datatypes.NOT_A_NUMBER
    # Note, using floor divison (//) to aid with `2to3` conversion
    result = ((datetime.day - 1) // 7) + 1
    return datatypes.number(result)


def day_in_week_function(context, date=None):
    """
    The date:day-in-week function returns a number representing the
    weekday of a given date. Sunday is 1, Saturday is 7.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, date, ('dateTime', 'date'))
    except ValueError:
        return datatypes.NOT_A_NUMBER
    # `_day_of_week()` is zero-based Sunday, EXSLT needs 1-based
    result = _day_of_week(datetime.year, datetime.month, datetime.day) + 1
    return datatypes.number(result)


def day_name_function(context, date=None):
    """
    The date:day-name function returns the full English day name of
    a given date.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, date, ('dateTime', 'date'))
    except ValueError:
        return datatypes.EMPTY_STRING
    weekday = _day_of_week(datetime.year, datetime.month, datetime.day)
    weekday = (u'Sunday', u'Monday', u'Tuesday', u'Wednesday', u'Thursday',
               u'Friday', u'Saturday')[weekday]
    return datatypes.string(weekday)


def day_abbreviation_function(context, date=None):
    """
    The date:day-abbreviation function returns the English abbreviation
    for the day name of a given date.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, date, ('dateTime', 'date'))
    except ValueError:
        return datatypes.EMPTY_STRING
    weekday = _day_of_week(datetime.year, datetime.month, datetime.day)
    weekday = (u'Sun', u'Mon', u'Tue', u'Wed', u'Thu', u'Fri', u'Sat')[weekday]
    return datatypes.string(weekday)


def hour_in_day_function(context, time=None):
    """
    The date:hour-in-date function returns the hour portion of a date-
    time string as an integer.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, time, ('dateTime', 'time'))
    except ValueError:
        return datatypes.NOT_A_NUMBER
    return datatypes.number(datetime.hour)


def minute_in_hour_function(context, time=None):
    """
    The date:minute-in-hour function returns the minute portion of a
    date-time string as an integer.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, time, ('dateTime', 'time'))
    except ValueError:
        return datatypes.NOT_A_NUMBER
    return datatypes.number(datetime.minute)


def second_in_minute_function(context, time=None):
    """
    The date:second-in-minute function returns the seconds portion
    of a date-time string as an integer.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, time, ('dateTime', 'time'))
    except ValueError:
        return datatypes.NOT_A_NUMBER
    return datatypes.number(datetime.second)

## EXSLT Other Functions (unstable) ##

_re_SimpleDateFormat = re.compile(r"(?P<symbol>([GyMdhHmsSEDFwWakKz])\2*)"
                                  r"|'(?P<escape>(?:[^']|'')*)'")

def FormatDate(context, datetime, pattern):
    """
    The date:format-date function formats a date/time according to a pattern.

    The first argument to date:format-date specifies the date/time to be
    formatted. It must be right or left-truncated date/time strings in one of
    the formats defined in XML Schema Part 2: Datatypes.  The permitted
    formats are as follows: xs:dateTime, xs:date, xs:time, xs:gYearMonth,
    xs:gYear, xs:gMonthDay, xs:gMonth and xs:gDay.

    The second argument is a string that gives the format pattern used to
    format the date. The format pattern must be in the syntax specified by
    the JDK 1.1 SimpleDateFormat class. The format pattern string is
    interpreted as described for the JDK 1.1 SimpleDateFormat class.

    Implements version 2.
    """
    try:
        datetime = _coerce(context, datetime, ('dateTime', 'date', 'time',
                                               'gYearMonth', 'gYear',
                                               'gMonthDay', 'gMonth', 'gDay'))
    except ValueError:
        return datatypes.EMPTY_STRING
    pattern = pattern.evaluate_as_string(context)

    # Fill in missing components for right-truncated formats
    if datetime.year is not None:
        if datetime.month is None:
            datetime.month = 1
        if datetime.day is None:
            datetime.day = 1
    if datetime.hour is None:
        datetime.hour = 0
    if datetime.minute is None:
        datetime.minute = 0
    if datetime.second is None:
        datetime.second = 0.0

    def repl(match):
        # NOTE: uses inherited `context` and `datetime` variables
        groups = match.groupdict()
        if groups['symbol'] is not None:
            symbol = groups['symbol']
            width = len(symbol)
            symbol = symbol[:1]
            if symbol == 'G':           # era designator
                if dateTime.year is None:
                    rt = u''
                elif dateTime.year > 0:
                    rt = u'AD'
                else:
                    rt = u'BC'
            elif symbol == 'y':         # year
                if dateTime.year is None:
                    rt = u''
                elif width > 2:
                    rt = u'%0.*d' % (width, dateTime.year)
                else:
                    rt = u'%0.2d' % (dateTime.year % 100)
            elif symbol == 'M':         # month in year
                if dateTime.month is None:
                    rt = u''
                elif width >= 4:
                    rt = MonthName(context, dateTime)
                elif width == 3:
                    rt = MonthAbbreviation(context, dateTime)
                else:
                    rt = u'%0.*d' % (width, dateTime.month)
            elif symbol == 'd':         # day in month
                if dateTime.day is None:
                    rt = u''
                else:
                    rt = u'%0.*d' % (width, dateTime.day)
            elif symbol == 'h':         # hour in am/pm (1-12)
                hours = dateTime.hour
                if hours > 12:
                    hours -= 12
                elif hours == 0:
                    hours = 12
                rt = u'%0.*d' % (width, hours)
            elif symbol == 'H':         # hour in day (0-23)
                rt = u'%0.*d' % (width, dateTime.hour)
            elif symbol == 'm':         # minute in hour
                rt = u'%0.*d' % (width, dateTime.minute)
            elif symbol =='s':          # second in minute
                rt = u'%0.*d' % (width, dateTime.second)
            elif symbol == 'S':         # millisecond
                fraction, second = math.modf(dateTime.second)
                fraction, millisecond = math.modf(fraction * 10**width)
                rt = u'%0.*d' % (width, millisecond + round(fraction))
            elif symbol == 'E':         # day in week
                if (dateTime.year is None or
                    dateTime.month is None or
                    dateTime.day is None):
                    rt = u''
                elif width >= 4:
                    rt = DayName(context, dateTime)
                else:
                    rt = DayAbbreviation(context, dateTime)
            elif symbol == 'D':         # day in year
                if (dateTime.year is None or
                    dateTime.month is None or
                    dateTime.day is None):
                    rt = u''
                else:
                    rt = u'%0.*d' % (width, DayInYear(context, dateTime))
            elif symbol == 'F':         # day of week in month
                if dateTime.day is None:
                    rt = u''
                else:
                    day_of_week = DayOfWeekInMonth(context, dateTime)
                    rt = u'%0.*d' % (width, day_of_week)
            elif symbol == 'w':         # week in year
                if (dateTime.year is None or
                    dateTime.month is None or
                    dateTime.day is None):
                    rt = u''
                else:
                    rt = u'%0.*d' % (width, WeekInYear(context, dataTime))
            elif symbol == 'W':         # week in month
                if (dateTime.year is None or
                    dateTime.month is None or
                    dateTime.day is None):
                    rt = u''
                else:
                    rt = u'%0.*d' % (width, WeekInMonth(context, dateTime))
            elif symbol == 'a':
                if dateTime.hour < 12:
                    rt = u'AM'
                else:
                    rt = u'PM'
            elif symbol == 'k':         # hour in day (1-24)
                rt = u'%0.*d' % (width, dateTime.hour + 1)
            elif symbol == 'K':         # hour in am/pm (0-11)
                hours = dateTime.hour
                if hours >= 12:
                    hours -= 12
                rt = u'%0.*d' % (width, hours)
            elif symbol == 'z':
                rt = dateTime.timezone or u''
            else:
                # not reached due to regular expression (supposedly)
                raise RuntimeException("bad format symbol '%s'" % symbol)
        elif groups['escape']:
            rt = groups['escape'].replace(u"''", u"'")
        else:
            # 'escape' group was empty, just matched '' (escaped single quote)
            rt = u"'"
        return rt

    return datatypes.string(_re_SimpleDateFormat.sub(repl, pattern))


def WeekInMonth(context, dateTime=None):
    """
    The date:week-in-month function returns the week in a month of a date as
    a number. If no argument is given, then the current local date/time, as
    returned by date:date-time is used the default argument. For the purposes
    of numbering, the first day of the month is in week 1 and new weeks begin
    on a Monday (so the first and last weeks in a month will often have less
    than 7 days in them).

    Implements version 3.
    """
    try:
        dateTime = _coerce(dateTime, ('dateTime', 'date'))
    except ValueError:
        return number.nan
    day_of_week = _dayOfWeek(dateTime.year, dateTime.month, dateTime.day)
    # _dayOfWeek returns 0=Sun, we need Sun=7
    day_of_week = ((day_of_week + 6) % 7) + 1
    week_offset = dateTime.day - day_of_week
    return (week_offset / 7) + (week_offset % 7 and 2 or 1)


def Difference(context, start, end):
    """
    The date:difference function returns the difference between the first date
    and the second date as a duration in string form.

    Implements version 1.
    """
    try:
        start = _coerce(start, ('dateTime', 'date', 'gYearMonth', 'gYear'))
        end = _coerce(end, ('dateTime', 'date', 'gYearMonth', 'gYear'))
    except ValueError:
        return u''
    return unicode(_difference(start, end))


def Add(context, dateTime, duration):
    """
    The date:add function returns the result of adding a duration to a dateTime.

    Implements version 2.
    """
    try:
        dateTime = _coerce(dateTime, ('dateTime', 'date', 'gYearMonth',
                                      'gYear'))
        duration = _Duration.parse(Conversions.StringValue(duration))
    except ValueError:
        return u''

    result = _DateTime()
    # Get the "adjusted" duration values
    if duration.negative:
        years, months, days, hours, minutes, seconds = (-duration.years,
                                                        -duration.months,
                                                        -duration.days,
                                                        -duration.hours,
                                                        -duration.minutes,
                                                        -duration.seconds)
    else:
        years, months, days, hours, minutes, seconds = (duration.years,
                                                        duration.months,
                                                        duration.days,
                                                        duration.hours,
                                                        duration.minutes,
                                                        duration.seconds)
    # Months (may be modified below)
    months += (dateTime.month or 1)
    carry, result.month = divmod(months - 1, 12)
    result.month += 1

    # Years (may be modified below)
    result.year = dateTime.year + years + carry

    # Timezone
    result.timezone = dateTime.timezone

    # Seconds
    seconds += (dateTime.second or 0)
    carry, result.second = divmod(seconds, 60)

    # Minutes
    minutes += (dateTime.minute or 0) + carry
    carry, result.minute = divmod(minutes, 60)

    # Hours
    hours += (dateTime.hour or 0) + carry
    carry, result.hour = divmod(hours, 24)

    # Days
    max_day = _daysInMonth(result.year, result.month)
    if dateTime.day > max_day:
        day = max_day
    if dateTime.day < 1:
        day = 1
    else:
        day = dateTime.day
    result.day = day + days + carry
    while True:
        max_day = _daysInMonth(result.year, result.month)
        if result.day > max_day:
            result.day -= max_day
            carry = 1
        elif result.day < 1:
            if result.month == 1:
                max_day = _daysInMonth(result.year - 1, 12)
            else:
                max_day = _daysInMonth(result.year, result.month - 1)
            result.day += max_day
            carry = -1
        else:
            break
        carry, result.month = divmod(result.month + carry - 1, 12)
        result.month += 1
        result.year += carry

    # Create output representation based in dateTime input
    # xs:gYear
    if dateTime.month is None:
        result = u'%0.4d%s' % (result.year, result.timezone or '')

    # xs:gYearMonth
    elif dateTime.day is None:
        result = u'%0.4d-%02d%s' % (result.year, result.month,
                                    result.timezone or '')

    # xs:date
    elif dateTime.hour is None:
        result = u'%0.4d-%02d-%02d%s' % (result.year, result.month, result.day,
                                         result.timezone or '')

    # xs:dateTime
    else:
        result = unicode(result)
    return result


def AddDuration(context, duration1, duration2):
    """
    The date:add-duration function returns the duration resulting from adding
    two durations together.

    Implements version 2.
    """
    duration1 = Conversions.StringValue(duration1)
    duration2 = Conversions.StringValue(duration2)
    try:
        duration1 = _Duration.parse(duration1)
        duration2 = _Duration.parse(duration2)
        duration = _addDurations(duration1, duration2)
    except ValueError:
        return u''

    return unicode(duration)


def Sum(context, nodeset):
    """
    The date:sum function adds a set of durations together. The string values
    of the nodes in the node set passed as an argument are interpreted as
    durations and added together as if using the date:add-duration function.

    Implements version 1.
    """
    if not isinstance(nodeset, XPathTypes.NodesetType):
        return u''
    try:
        strings = map(Conversions.StringValue, nodeset)
        durations = map(_Duration.parse, strings)
        duration = _addDurations(*durations)
    except ValueError:
        return u''

    return unicode(duration)


def Seconds(context, string=None):
    """
    The date:seconds function returns the number of seconds specified by the
    argument string. If no argument is given, then the current local
    date/time, as returned by date:date-time is used as a default argument.

    Implements version 1.
    """
    if string is None:
        string = str(_DateTime.now())
    else:
        string = Conversions.StringValue(string)

    try:
        if 'P' in string:
            # its a duration
            duration = _Duration.parse(string)
        else:
            # its a dateTime
            dateTime = _DateTime.parse(string, ('dateTime', 'date',
                                                'gYearMonth', 'gYear'))
            duration = _difference(_EPOCH, dateTime)
    except ValueError:
        return number.nan

    # The number of years and months must both be equal to zero
    if duration.years or duration.months:
        return number.nan

    # Convert the duration to just seconds
    seconds = (duration.days * 86400 + duration.hours * 3600 +
               duration.minutes * 60 + duration.seconds )
    if duration.negative:
        seconds *= -1
    return seconds


def Duration(context, seconds=None):
    """
    The date:duration function returns a duration string representing the
    number of seconds specified by the argument string. If no argument is
    given, then the result of calling date:seconds without any arguments is
    used as a default argument.

    Implements version 1.
    """
    if seconds is None:
        # The epoch for EXSLT is 1970-01-01T00:00:00Z
        # FIXME: we could code around this, but most (all?) platforms we
        # support have a time() epoch of 1970-01-01, so why bother.
        if time.mktime((1970, 1, 1, 0, 0, 0, 0, 0, 0)) != time.timezone:
            warnings.warn("platform epoch != 1970-01-01", RuntimeWarning)
        # Don't use fractional seconds to keep with constructed dateTimes
        seconds = int(time.time())
    else:
        seconds = Conversions.NumberValue(seconds)
        if not number.finite(seconds):
            # +/-Inf or NaN
            return u''
    duration = _Duration(negative=(seconds < 0), seconds=abs(seconds))
    return unicode(duration)


## XSLT Extension Module Interface ####################################

extension_namespaces = {
    EXSL_DATE_TIME_NS : 'date',
    }

extension_functions = {
    # Core Functions
    (EXSL_DATE_TIME_NS, 'date-time'): date_time_function,
    (EXSL_DATE_TIME_NS, 'date'): date_function,
    (EXSL_DATE_TIME_NS, 'time'): time_function,
    (EXSL_DATE_TIME_NS, 'year'): year_function,
    (EXSL_DATE_TIME_NS, 'leap-year'): leap_year_function,
    (EXSL_DATE_TIME_NS, 'month-in-year'): month_in_year_function,
    (EXSL_DATE_TIME_NS, 'month-name'): month_name_function,
    (EXSL_DATE_TIME_NS, 'month-abbreviation'): month_abbreviation_function,
    (EXSL_DATE_TIME_NS, 'week-in-year'): week_in_year_function,
    (EXSL_DATE_TIME_NS, 'day-in-year'): day_in_year_function,
    (EXSL_DATE_TIME_NS, 'day-in-month'): day_in_month_function,
    (EXSL_DATE_TIME_NS, 'day-of-week-in-month'): day_of_week_in_month_function,
    (EXSL_DATE_TIME_NS, 'day-in-week'): day_in_week_function,
    (EXSL_DATE_TIME_NS, 'day-name'): day_name_function,
    (EXSL_DATE_TIME_NS, 'day-abbreviation'): day_abbreviation_function,
    (EXSL_DATE_TIME_NS, 'hour-in-day'): hour_in_day_function,
    (EXSL_DATE_TIME_NS, 'minute-in-hour'): minute_in_hour_function,
    (EXSL_DATE_TIME_NS, 'second-in-minute'): second_in_minute_function,
    # Other Functions
    (EXSL_DATE_TIME_NS, 'format-date'): format_date_function,
    #(EXSL_DATE_TIME_NS, 'parse-date'): parse_date_function,
    (EXSL_DATE_TIME_NS, 'week-in-month'): week_in_month_function,
    (EXSL_DATE_TIME_NS, 'difference'): difference_function,
    (EXSL_DATE_TIME_NS, 'add'): add_function,
    (EXSL_DATE_TIME_NS, 'add-duration'): add_duration_function,
    (EXSL_DATE_TIME_NS, 'sum'): sum_function,
    (EXSL_DATE_TIME_NS, 'seconds'): seconds_function,
    (EXSL_DATE_TIME_NS, 'duration'): duration_function,
    }

extension_elements = {
    #(EXSL_DATE_TIME_NS, 'date-format'): date_format_element
    }


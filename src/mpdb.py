import sys
import gc


class MpdbQuit(Exception):
    pass


class Mbdb:
    def __init__(self):
        self.botframe = None
        self.breaks = {}
        self.quitting = False
        self.currentbp = None
        self.stopframe = None
        self.curframe = None
        self.stoplineno = -1

    def reset(self):
        self.botframe = None
        self._set_stopinfo(None, None)
        self.curframe = None

    def run(self, cmd):
        self.reset()

    def trace_dispatch(self, frame, event, arg):
        self.curframe = frame
        if self.quitting:
            return  # None
        if event == 'line':
            return self.dispatch_line(frame)
        if event == 'call':
            return self.dispatch_call(frame, arg)
        # if event == 'return':
        #     return self.dispatch_return(frame, arg)
        # if event == 'exception':
        #     return self.dispatch_exception(frame, arg)
        # print('bdb.Bdb.dispatch: unknown debugging event:', repr(event))
        return self.trace_dispatch

    def dispatch_line(self, frame):
        if self.stop_here(frame) or self.break_here(frame):
            self.user_line(frame)
            if self.quitting:
                raise MpdbQuit
        return self.trace_dispatch

    def dispatch_call(self, frame, arg):
        if self.botframe is None:
            # First call of dispatch since reset()
            self.botframe = frame.f_back  # (CT) Note that this may also be None!
            return self.trace_dispatch
        if not (self.stop_here(frame) or self.break_anywhere(frame)):
            # No need to trace this function
            return  # None
        self.user_call(frame, arg)
        return self.trace_dispatch

    # def dispatch_return(self, frame, arg):
    #     pass

    def get_break(self, filename, lineno):
        """Return True if there is a breakpoint for filename:lineno."""
        return filename in self.breaks \
               and lineno in self.breaks[filename]

    def get_breaks(self, filename, lineno):
        """Return all breakpoints for filename:lineno.
        If no breakpoints are set, return an empty list.
        """
        return filename in self.breaks \
               and lineno in self.breaks[filename] \
               and Breakpoint.bplist[filename, lineno] or []

    def break_here(self, frame):
        filename = frame.f_code.co_filename
        if filename not in self.breaks:
            return False
        lineno = frame.f_lineno
        if lineno not in self.breaks[filename]:
            # The line itself has no breakpoint, but maybe the line is the
            # first line of a function with breakpoint set by function name.
            lineno = frame.f_code.co_firstlineno
            if lineno not in self.breaks[filename]:
                return False

        # flag says ok to delete temp. bp
        bp, flag = effective(filename, lineno, frame)
        if bp:
            self.currentbp = bp.number
            if flag and bp.temporary:
                self.do_clear(str(bp.number))
            return True
        else:
            return False

    def do_clear(self, arg):
        raise NotImplementedError("Subclass of BDB must implement this functionality")

    def clear_all_breaks(self):
        """Delete all existing breakpoints.
        If none were set, return an error message.
        """
        if not self.breaks:
            return 'There are no breakpoints'
        for bp in Breakpoint.bpbynumber:
            if bp:
                bp.deleteMe()
        self.breaks = {}
        return None

    def stop_here(self, frame):
        if frame is self.stopframe:
            if self.stoplineno == -1:
                return False
            return frame.f_lineno >= self.stoplineno
        if not self.stopframe:
            return True
        return False

    def set_next(self, frame):
        self._set_stopinfo(frame, None)

    def set_step(self):
        self._set_stopinfo(None, None)

    def set_return(self, frame):
        self._set_stopinfo(frame.f_back, frame)

    def set_continue(self):
        """Stop only at breakpoints or when finished.
                If there are no breakpoints, set the system trace function to None.
                """
        # Don't stop except at breakpoints or when finished
        self._set_stopinfo(self.botframe, None, -1)
        if not self.breaks:
            sys.settrace(None)

    def set_until(self, frame, lineno=None):
        """Stop when the line with the lineno greater than the current one is
        reached or when returning from current frame."""
        # the name "until" is borrowed from gdb
        if lineno is None:
            lineno = frame.f_lineno + 1
        self._set_stopinfo(frame, frame, lineno)

    def set_break(self, filename, lineno, temporary=False, cond=None):
        bp_list = self.breaks.setdefault(filename, [])
        if lineno not in bp_list:
            bp_list.append(lineno)
        bp = Breakpoint(filename, lineno, temporary, cond)
        return None

    def set_quit(self):
        """Set quitting attribute to True.
        Raises BdbQuit exception in the next call to a dispatch_*() method.
        """
        self.stopframe = self.botframe
        self.returnframe = None
        self.quitting = True
        sys.settrace(None)

    def break_anywhere(self, frame) -> bool:
        return frame.f_code.co_filename in self.breaks

    def clear_break(self, filename, lineno):
        """Delete breakpoints for filename:lineno.
        If no breakpoints were set, return an error message.
        """
        if filename not in self.breaks:
            return 'There are no breakpoints in %s' % filename
        if lineno not in self.breaks[filename]:
            return 'There is no breakpoint at %s:%d' % (filename, lineno)
        for bp in Breakpoint.bplist[filename, lineno][:]:
            bp.deleteMe()
        self._prune_breaks(filename, lineno)

    def clear_bpbynumber(self, arg):
        """Delete a breakpoint by its index in Breakpoint.bpbynumber.
        If arg is invalid, return an error message.
        """
        try:
            bp = self.get_bpbynumber(arg)
        except ValueError as err:
            return str(err)
        bp.deleteMe()
        self._prune_breaks(bp.file, bp.line)
        return None

    def get_bpbynumber(self, arg):
        """Return a breakpoint by its index in Breakpoint.bybpnumber.
        For invalid arg values or if the breakpoint doesn't exist,
        raise a ValueError.
        """
        if not arg:
            raise ValueError('Breakpoint number expected')
        try:
            number = int(arg)
        except ValueError:
            raise ValueError('Non-numeric breakpoint number %s' % arg) from None
        try:
            bp = Breakpoint.bpbynumber[number]
        except IndexError:
            raise ValueError('Breakpoint number %d out of range' % number) from None
        if bp is None:
            raise ValueError('Breakpoint %d already deleted' % number)
        return bp

    def _prune_breaks(self, filename, lineno):
        """Prune breakpoints for filename:lineno.
        A list of breakpoints is maintained in the Bdb instance and in
        the Breakpoint class.  If a breakpoint in the Bdb instance no
        longer exists in the Breakpoint class, then it's removed from the
        Bdb instance.
        """
        if (filename, lineno) not in Breakpoint.bplist:
            self.breaks[filename].remove(lineno)
        if not self.breaks[filename]:
            del self.breaks[filename]

    def _set_stopinfo(self, stopframe, returnframe, stoplineno=0):
        """Set the attributes for stopping.
        If stoplineno is greater than or equal to 0, then stop at line
        greater than or equal to the stopline.  If stoplineno is -1, then
        don't stop at all.
        """
        self.stopframe = stopframe
        self.returnframe = returnframe
        self.quitting = False
        # stoplineno >= 0 means: stop at line >= the stoplineno
        # stoplineno -1 means: don't stop at all
        self.stoplineno = stoplineno

    def set_trace(self):
        sys.settrace(self.trace_dispatch)

    def user_line(self, frame):
        pass

    def user_call(self, frame, arg):
        pass


# Determines if there is an effective (active) breakpoint at this
# line of code.  Returns breakpoint number or 0 if none
def effective(file, line, frame):
    """Determine which breakpoint for this file:line is to be acted upon.
    Called only if we know there is a breakpoint at this location.  Return
    the breakpoint that was triggered and a boolean that indicates if it is
    ok to delete a temporary breakpoint.  Return (None, None) if there is no
    matching breakpoint.
    """
    possibles = Breakpoint.bplist[file, line]
    for b in possibles:
        if not b.enabled:
            continue
        # Count every hit when bp is enabled
        b.hits += 1
        if not b.cond:
            # If unconditional, and ignoring go on to next, else break
            if b.ignore > 0:
                b.ignore -= 1
                continue
            else:
                # breakpoint and marker that it's ok to delete if temporary
                return b, True
        else:
            # Conditional bp.
            # Ignore count applies only to those bpt hits where the
            # condition evaluates to true.
            try:
                # Even tho MicroPython eval statement is limited
                # to just globals it is till useful
                val = eval(b.cond, frame.f_globals, frame.f_globals)
                if val:
                    if b.ignore > 0:
                        b.ignore -= 1
                        # continue
                    else:
                        return b, True
                # else:
                #   continue
            except:
                # if eval fails, most conservative thing is to stop on
                # breakpoint regardless of ignore count.  Don't delete
                # temporary, as another hint to user.
                return b, False
    return None, None


# noinspection DuplicatedCode
class Breakpoint:
    """Breakpoint class.
    Implements temporary breakpoints, ignore counts, disabling and
    (re)-enabling, and conditionals.
    Breakpoints are indexed by number through bpbynumber and by
    the (file, line) tuple using bplist.  The former points to a
    single instance of class Breakpoint.  The latter points to a
    list of such instances since there may be more than one
    breakpoint per line.
    When creating a breakpoint, its associated filename should be
    in canonical form.  If funcname is defined, a breakpoint hit will be
    counted when the first line of that function is executed.  A
    conditional breakpoint always counts a hit.
    """

    # XXX Keeping state in the class is a mistake -- this means
    # you cannot have more than one active Bdb instance.

    next = 1  # Next bp to be assigned
    bplist = {}  # indexed by (file, lineno) tuple
    bpbynumber = [None]  # Each entry is None or an instance of Bpt

    # index 0 is unused, except for marking an
    # effective break .... see effective()

    def __init__(self, file, line, temporary=False, cond=None):
        self.func_first_executable_line = None
        self.file = file  # This better be in canonical form!
        self.line = line
        self.temporary = temporary
        self.cond = cond
        self.enabled = True
        self.ignore = 0
        self.hits = 0
        self.number = Breakpoint.next
        Breakpoint.next += 1
        # Build the two lists
        self.bpbynumber.append(self)
        if (file, line) in self.bplist:
            self.bplist[file, line].append(self)
        else:
            self.bplist[file, line] = [self]

    def deleteMe(self):
        """Delete the breakpoint from the list associated to a file:line.
        If it is the last breakpoint in that position, it also deletes
        the entry for the file:line.
        """

        index = (self.file, self.line)
        self.bpbynumber[self.number] = None  # No longer in list
        self.bplist[index].remove(self)
        if not self.bplist[index]:
            # No more bp for this f:l combo
            del self.bplist[index]

    def enable(self):
        """Mark the breakpoint as enabled."""
        self.enabled = True

    def disable(self):
        """Mark the breakpoint as disabled."""
        self.enabled = False

    def bpprint(self, out=None):
        """Print the output of bpformat().
        The optional out argument directs where the output is sent
        and defaults to standard output.
        """
        if out is None:
            out = sys.stdout
        print(self.bpformat(), file=out)

    def bpformat(self):
        """Return a string with information about the breakpoint.
        The information includes the breakpoint number, temporary
        status, file:line position, break condition, number of times to
        ignore, and number of times hit.
        """
        if self.temporary:
            disp = 'del  '
        else:
            disp = 'keep '
        if self.enabled:
            disp = disp + 'yes  '
        else:
            disp = disp + 'no   '
        ret = '%-4dbreakpoint   %s at %s:%d' % (self.number, disp,
                                                self.file, self.line)
        if self.cond:
            ret += '\n\tstop only if %s' % (self.cond,)
        if self.ignore:
            ret += '\n\tignore next %d hits' % (self.ignore,)
        if self.hits:
            if self.hits > 1:
                ss = 's'
            else:
                ss = ''
            ret += '\n\tbreakpoint already hit %d time%s' % (self.hits, ss)
        return ret

    def __str__(self):
        """Return a condensed description of the breakpoint."""
        return 'breakpoint %s at %s:%s' % (self.number, self.file, self.line)


    
# Adapted from: https://github.com/micropython/micropython-lib/blob/master/cmd/cmd.py
class Cmd:
    IDENTCHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_'
    PROMPT = '(Mpdb) '
    doc_leader = ""
    doc_header = "Documented commands (type help <topic>):"
    misc_header = "Miscellaneous help topics:"
    undoc_header = "Undocumented commands:"
    nohelp = "*** No help on %s"
    ruler = '='

    def __init__(self):
        self.lastcmd = ''

    def cmdloop(self):
        """Repeatedly issue a prompt, accept input, parse an initial prefix
        off the received input, and dispatch to action methods, passing them
        the remainder of the line as argument.
        """
        try:
            stop = None
            while not stop:
                try:
                    line = input(self.PROMPT)
                except EOFError:
                    line = 'EOF'
                stop = self.onecmd(line)
        finally:
            pass

    def onecmd(self, line):
        """Interpret the argument as though it had been typed in response
        to the prompt.
        This may be overridden, but should not normally need to be;
        see the precmd() and postcmd() methods for useful execution hooks.
        The return value is a flag indicating whether interpretation of
        commands by the interpreter should stop.
        """
        cmd, arg, line = self.parseline(line)
        if not line:
            return self.emptyline()
        if cmd is None:
            return self.default(line)
        self.lastcmd = line
        if line == 'EOF':
            self.lastcmd = ''
        if cmd == '':
            return self.default(line)
        else:
            try:
                func = getattr(self, 'do_' + cmd)
            except AttributeError:
                return self.default(line)
            return func(arg)

    def parseline(self, line):
        """Parse the line into a command name and a string containing
        the arguments.  Returns a tuple containing (command, args, line).
        'command' and 'args' may be None if the line couldn't be parsed.
        """
        line = line.strip()
        if not line:
            return None, None, line
        elif line[0] == '?':
            line = 'help ' + line[1:]
        elif line[0] == '!':
            if hasattr(self, 'do_shell'):
                line = 'shell ' + line[1:]
            else:
                return None, None, line
        i, n = 0, len(line)
        while i < n and line[i] in self.IDENTCHARS:
            i = i + 1
        cmd, arg = line[:i], line[i:].strip()
        return cmd, arg, line

    def default(self, line):
        """Called on an input line when the command prefix is not recognized.
        If this method is not overridden, it prints an error message and
        returns.
        """
        sys.stdout.write('*** Unknown syntax: %s\n' % line)

    def emptyline(self):
        """Called when an empty line is entered in response to the prompt.
        If this method is not overridden, it repeats the last nonempty
        command entered.
        """
        if self.lastcmd:
            return self.onecmd(self.lastcmd)

    def get_names(self):
        # This method used to pull in base class attributes
        # at a time dir() didn't do it yet.
        return dir(self.__class__)

    def do_help(self, arg):
        """List available commands with "help" or detailed help with "help cmd"."""
        if arg:
            # XXX check arg syntax
            try:
                func = getattr(self, 'help_' + arg)
            except AttributeError:
                sys.stdout.write("%s\n" % str(self.nohelp % (arg,)))
                return
            func()
        else:
            names = self.get_names()
            cmds_doc = []
            cmds_undoc = []
            help = {}
            for name in names:
                if name[:5] == 'help_':
                    help[name[5:]] = 1
            names.sort()
            # There can be duplicates if routines overridden
            prevname = ''
            for name in names:
                if name[:3] == 'do_':
                    if name == prevname:
                        continue
                    prevname = name
                    cmd = name[3:]
                    if cmd in help:
                        cmds_doc.append(cmd)
                        del help[cmd]
                    else:
                        cmds_undoc.append(cmd)
            sys.stdout.write("%s\n" % str(self.doc_leader))
            self.print_topics(self.doc_header, cmds_doc, 15, 80)
            self.print_topics(self.misc_header, list(help.keys()), 15, 80)
            self.print_topics(self.undoc_header, cmds_undoc, 15, 80)

    def print_topics(self, header, cmds, cmdlen, maxcol):
        if cmds:
            sys.stdout.write("%s\n" % str(header))
            if self.ruler:
                sys.stdout.write("%s\n" % str(self.ruler * len(header)))
            for cmd in cmds:
                print(cmd)
            sys.stdout.write("\n")


def print_stacktrace(frame, level=0):
    print("%2d: %s@%s:%s => %s:%d" % (
        level, "  ",
        frame.f_globals['__name__'],
        frame.f_code.co_name,
        # reduce full path to some pseudo-relative
        'misc' + ''.join(frame.f_code.co_filename.split('tests/misc')[-1:]),
        frame.f_lineno,
    ))

    if frame.f_back:
        print_stacktrace(frame.f_back, level + 1)


class Mpdb(Mbdb, Cmd):
    def do_break(self, arg, temporary=False):
        if not arg:
            if self.breaks:  # There's at least one
                self.message("Num Type         Disp Enb   Where")
                for bp in Breakpoint.bpbynumber:
                    if bp:
                        self.message(bp.bpformat())
            return
        filename = None
        lineno = None
        cond = None
        comma = arg.find(',')
        if comma > 0:
            # parse stuff after comma: "condition"
            cond = arg[comma + 1:].lstrip()
            arg = arg[:comma].rstrip()
        # parse stuff before comma: [filename:]lineno | function
        colon = arg.rfind(':')
        funcname = None
        if colon >= 0:
            filename = arg[:colon].rstrip()
            print(filename)
            arg = arg[colon + 1:].lstrip()
            try:
                lineno = int(arg)
            except ValueError:
                return
        self.set_break(filename, lineno, cond=cond, temporary=temporary)

    def do_clear(self, arg):
        """cl(ear) filename:lineno\ncl(ear) [bpnumber [bpnumber...]]
        With a space separated list of breakpoint numbers, clear
        those breakpoints.  Without argument, clear all breaks (but
        first ask confirmation).  With a filename:lineno argument,
        clear all breaks at that line in that file.
        """
        if not arg:
            try:
                reply = input('Clear all breaks? ')
            except EOFError:
                reply = 'no'
            reply = reply.strip().lower()
            if reply in ('y', 'yes'):
                bplist = [bp for bp in Breakpoint.bpbynumber if bp]
                self.clear_all_breaks()
                for bp in bplist:
                    self.message('Deleted %s' % bp)
            return
        if ':' in arg:
            # Make sure it works for "clear C:\foo\bar.py:12"
            i = arg.rfind(':')
            filename = arg[:i]
            arg = arg[i + 1:]
            try:
                lineno = int(arg)
            except ValueError:
                err = "Invalid line number (%s)" % arg
            else:
                bplist = self.get_breaks(filename, lineno)
                err = self.clear_break(filename, lineno)
            if err:
                self.error(err)
            else:
                for bp in bplist:
                    self.message('Deleted %s' % bp)
            return
        numberlist = arg.split()
        for i in numberlist:
            try:
                bp = self.get_bpbynumber(i)
            except ValueError as err:
                self.error(err)
            else:
                self.clear_bpbynumber(i)
                self.message('Deleted %s' % bp)

    do_cl = do_clear  # 'c' is already an abbreviation for 'continue'

    def do_step(self, arg):
        """s(tep)
        Execute the current line, stop at the first possible occasion
        (either in a function that is called or in the current
        function).
        """
        self.set_step()
        return 1

    do_s = do_step

    def do_next(self, arg):
        """n(ext)
        Continue execution until the next line in the current function
        is reached or it returns.
        """
        self.set_next(self.curframe)
        return 1

    do_n = do_next

    def do_continue(self, arg):
        """c(ont(inue))
        Continue execution, only stop when a breakpoint is encountered.
        """
        self.set_continue()
        return 1

    do_c = do_cont = do_continue

    def do_where(self, arg):
        """w(here)
        Print a stack trace.
        """
        print_stacktrace(self.curframe)
        self.cmdloop()
        return 1

    do_w = do_where

    def do_until(self, arg):
        """unt(il) [lineno]
        Without argument, continue execution until the line with a
        number greater than the current one is reached.  With a line
        number, continue execution until a line with a number greater
        or equal to that is reached.  In both cases, also stop when
        the current frame returns.
        """
        if arg:
            try:
                lineno = int(arg)
            except ValueError:
                self.error('Error in argument: %r' % arg)
                return
            if lineno <= self.curframe.f_lineno:
                self.error('"until" line number is smaller than current '
                           'line number')
                return
        else:
            lineno = None
        self.set_until(self.curframe, lineno)
        return 1

    do_unt = do_until

    def do_tbreak(self, arg):
        self.do_break(arg, True)

    def message(self, msg):
        print(msg)

    def error(self, msg):
        print('***', msg)

    def do_quit(self, arg):
        self.set_quit()
        return 1

    do_q = do_quit

    def do_mem_free(self, arg):
        print('Memory Free: ', gc.mem_free())

    do_mf = do_mem_free

    def do_mem_alloc(self, arg):
        print('Memory Allocated: ', gc.mem_alloc())

    do_ma = do_mem_alloc

    def do_collect(self, arg):
        gc.collect()
        print('Garbage Collected!', )

    def do_p(self, arg):
        repr(self._getval(arg))

    def _getval(self, arg):
        return eval(arg, self.curframe.f_globals, self.curframe.f_globals)

    def user_line(self, frame):
        out_info = '{}:{}'.format(frame.f_code.co_filename, frame.f_lineno)
        if self.currentbp is not 0:
            out_info = 'BREAK ' + out_info
            self.currentbp = 0
        else:
            out_info = 'STOP ' + out_info
        print(out_info)
        self.cmdloop()

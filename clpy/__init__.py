#!/usr/bin/env python
import argparse
import subprocess
import re
import os
import keyword
import builtins
import pickle

program_name = "clpy"
description = """Convert a CLI to a python module."""
version = "0.0.1"

clpydir = os.path.dirname(__file__)

flag_name = "f"
# man_text = subprocess.getoutput("man -P cat "+args.command).split("\n")
# todo: It might be better to have a base class + kwargs
class_fmt = """# clpy generated, do not modify by hand
import clpy.__cli__ as cli
from clpy import clpydir
import pickle
import os
from enum import Enum, auto

class cli_{cmd}(cli.cli):
    \"\"\"
{usage}{docargs}{docflags}
    \"\"\"
    __options = pickle.load(open(os.path.join(clpydir, "{cmd}_options.pkl"), "rb"))
    def __init__(self, *in_flags):
        self.__cmd = {usage_cmd}
        self.__g_flags = {g_flags}
        super().__init__(self.__cmd, self.__options, self.__g_flags, *in_flags)
        pass
    def add_flags(self, *in_flags):
        \"\"\"
{docflags2}
        \"\"\"
        super().add_flags(self, *in_flags)
        pass
    class {f}(Enum):
{enum}
        pass
"""

class reg:
    usage = re.compile("^(?:usage:) ([A-Z0-9]+)\s+", re.IGNORECASE)
    whitespace = re.compile("^\s")
    ellipsis = re.compile("^ ?\.\.\.")
    start_optional = re.compile("^ ?\[")
    end_optional = re.compile("^ ?\]")
    start_enum = re.compile("^ ?\{")
    end_enum = re.compile("^ ?\}")
    switch = re.compile("^(?:\s+)?(--?[A-Za-z0-9\-#_]+)")
    has_arg = re.compile("^\s{2,8}(?!---)(-{0,2}[A-Z])", re.IGNORECASE)
    argument = re.compile("^(?: |=)?((?!-)<?[A-Za-z0-9\-#_]+>?)")
    equals = re.compile("^(=|\[=)")
    comma = re.compile("^, ?")
    or_ = re.compile("^(?: ?\|) ?")
    stop = re.compile("^\s\s")

class OptionMeta:
    def str(option):
        out = []
        just = 16
        if option.lines:
            out.append("["+"".ljust(64,'-')+"]")
            out.append("["+option.name.center(64,'-')+"]")
            out.append("["+"".ljust(64,'-')+"]")
            out.append("original line/s:")
            out.append("'\n".join([f"line {n}: '{l}" for n, l in option.lines])+"'\n")
        if option.usage:
            out.append("usage:".ljust(just)+option.usage)
            if option.bad_match: out.append("bad_match:".ljust(just)+str(option.bad_match)+": "+option.bad_match_reason)
            if option.wants_equals: out.append("equals: ".ljust(just)+str(option.wants_equals))
            if option.is_positional: out.append("is_positional: ".ljust(just)+str(option.is_positional))
        if option.switch:
            out.append("switch:".ljust(just)+str(option.switch.groups()[0]))
        if option.nargs:
            out.append("nargs:".ljust(just)+str(option.nargs))
        if option.arguments:
            out.append("arguments:".ljust(just)+", ".join([f.to_str() for f in option.arguments]))
        if option.children:
            out.append("["+"children".center(64,'-')+"]")
            out.extend([OptionMeta.str(c) for c in option.children])
        if option.doc:
            tab = "".ljust(just, " ")
            out.append("docs:".ljust(just)+("\n"+tab).join(option.doc))
        else:
            out.append("["+"".ljust(64,'-')+"]")
        return "\n".join(out)

def debug_print(prologue, unused, options, usage, name, verbose, no_bad_matches):
    print("".ljust(128, "="))
    print(f" {name} ".center(128, "="))
    print("".ljust(128, "="))
    if verbose and usage:
        print(" usage ".center(128, "_"))
        print("\n".join([f"line {n}: {l}" for n, l in usage.lines]))
        for option in usage.options:
            print(OptionMeta.str(option))
    print("")
    if verbose and prologue:
        print(" prologue ".center(128, "_"))
        print("\n".join(prologue))
    print("")
    print(" options ".center(128, "_"))
    if not no_bad_matches:
        print("".ljust(128, "-"))
        print(" bad matches ".center(128, "-"))
        print("".ljust(128, "-"))
        print("")
        for o in options:
            if o.bad_match:
                print(OptionMeta.str(o))
                print("")
        print("")
    print("".ljust(128, "-"))
    print(" good matches ".center(128, "-"))
    print("".ljust(128, "-"))
    print("")
    for o in options:
        if not o.bad_match:
            print(OptionMeta.str(o))
            print("")
    print("")
    print("".ljust(64, "-"))
    print("")
    if verbose:
        print("\n".join(unused))

class Command:
    name = ""
    usage = ""
    options = None
    
    def __init__(self):
        options = []
        pass
    
class Argument:
    is_optional = False # else is positional
    wants_equals = False
    default = None
    choices = None
    def to_str(self):
        out = ", ".join([m.groups()[0] for m in self.choices])
        if len(self.choices) > 1:
            out = "{"+out+"}"
        if self.is_optional:
            out = f"[{out}]"
        return out
            
    def __init__(self, match, is_optional = False, wants_equals = False):
        self.is_optional = is_optional
        self.wants_equals = wants_equals
        self.match = match
        self.choices = [match]
    
class Option:
    name = None
    lines = None
    doc = None
    usage = None
    arguments = None
    matches = None
    nargs = None
    switch = None
    parent = None
    children = None
    span = None
    bad_match = False
    bad_match_reason = ""
    ellipsis = False
    wants_equals = False
    option_depth = 0
    enum_depth = 0
    all_names = {}
    is_parent = False
    is_positional = False

    def __init__(self):
        self.lines = []
        self.doc = []
        self.matches = []
        self.children = []
        self.arguments = []
        pass

    def to_dict(self):
        return {
            o.name : {
                "switch": o.switch.group(1),
                "nargs": o.nargs,
                "wants_equals": o.wants_equals
            }
            for o in [self, *self.children]
        }

class Usage:
    cmd = None
    match = None
    matches = None
    options = None
    lines = None

    def __init__(self):
        self.lines = []
        self.matches = []
        self.options = []

        
        
def option_add_nargs(option):
    args = option.arguments
    ellipsis = option.ellipsis
    if args:
        if not any([a.is_optional for a in args]) and not ellipsis:
            option.nargs = str(len(args))
        elif len(args) == 1 and args[0].is_optional and not ellipsis:
            option.nargs = "?"
        elif all([a.is_optional for a in args]) and ellipsis:
            option.nargs = "*"
        elif len(args) > 1 and not args[0].is_optional and all([a.is_optional for a in args[1:]]) and ellipsis:
            option.nargs = "+"
        elif all([not a.is_optional for a in args]) and ellipsis:
            option.nargs = "A..."
    elif ellipsis:
        option.nargs = "..."


def parse_option(line, pos, line_num, match):
    option = Option()
    option.is_parent = True
    option.lines.append((line_num, line))
    option.span = (pos + match.span(1)[0], pos + match.span(1)[1])
    option.switch = match
    child = option
    argument = None

    # Start searching for options etc.
    while(match):

        # Check to see if we've moved out of scope
        if child.option_depth < 0: break
        if child.enum_depth < 0: break

        child.matches.append(match)
        pos += match.span()[1]

        # Are we done?
        if not line[pos:]: break

        # Handle arguments
        if match := reg.argument.search(line[pos:]):

            if wants_equals := bool(reg.equals.search(line[pos:])):
                child.wants_equals = True

            if argument and child.enum_depth != 0:
                argument.choices.append(match)
            else:
                argument = Argument(match, child.option_depth != 0, wants_equals)
                child.arguments.append(argument)
                argument = argument if child.enum_depth != 0 else None

        # Handle child options
        elif match := reg.switch.search(line[pos:]):
            if child.option_depth:
                # throw this child out,
                # it's not a part of this option.
                child.bad_match = True
                child.bad_match_reason = "attempted optional child switch, not supported."
                child.option_depth = 0
                break
            option_add_nargs(child)
            child = Option()
            option.children.append(child)
            child.parent = option
            child.switch = match
            child.span = (pos, pos+match.span(1)[1])

        # Handle brackets
        elif match := reg.start_optional.search(line[pos:]): child.option_depth += 1
        elif match := reg.end_optional.search(line[pos:]): child.option_depth -= 1
        elif match := reg.start_enum.search(line[pos:]): child.enum_depth += 1
        elif match := reg.end_enum.search(line[pos:]): child.enum_depth -= 1

        # Handle syntactic sugar
        elif match := reg.ellipsis.search(line[pos:]): child.ellipsis = True
        elif match := reg.equals.search(line[pos:]): child.wants_equals = True
        elif match := reg.comma.search(line[pos:]): pass
        elif match := reg.or_.search(line[pos:]): pass
        elif match := reg.stop.search(line[pos:]):
            pos += match.span()[1]
            break

        if not match:
            # Something went wrong.
            # Reverting to start pos.
            pos = option.span[1]
            option.bad_match = True
            option.bad_match_reason = "Couldn't find a valid match"
            break

    option_add_nargs(child)
    # todo: this is a hack to fix cases switch usage isn't explained in the parent.
    # it would probably be better to split each child into it's own long+short option
    # when creating modules.
    for child in option.children:
        if child.nargs and not option.nargs:
            option.nargs = child.nargs
        # if child.wants_equals and not option.wants_equals:
        #     option.wants_equals = child.wants_equals

    opt_usage, doc = line[option.span[0]:pos], line[pos:]
    if doc.strip(): option.doc.append(doc.strip())
    option.usage = opt_usage.strip()
    for o in [option, *option.children]:
        o.name = o.switch.group(1).lstrip("-")
        o.name = o.name.replace("-", "_")
        if o.name in keyword.kwlist: o.name = o.name+"_"
        if o.name in dir(builtins): o.name = o.name+"_"
        o.name = o.name
        if o.name not in Option.all_names:
            Option.all_names[o.name] = o
        else:
            # we can't allow two flags with the same name
            o.bad_match = True
            o.bad_match_reason = f"The name '{o.name}' already exists"
            # todo: consider appending doc strings or something?
        if not o.name:
            o.bad_match = True
            o.bad_match_reason = f"The name was empty!"
        pass
    option.is_positional = not option.children and not option.nargs and not option.switch.group(1).startswith("-")
    return option, pos


def parse_man(text, start = 0):
    id_synopsis = text.index("SYNOPSIS")
    id_description = text.index("DESCRIPTION")
    start = id_synopsis+1
    end = id_description
    re_title = re.compile("^[A-Z]+")
    # adding usage to better match what parse_usage expects
    text[start] = "Usage: "+text[start].lstrip()
    usage, _, _ = parse_usage(text, start=start)
    sections = []
    start = end
    current = ""
    for line in text[start:]:
        if match := re_title.search(line):
            if current not in ["EXAMPLES"]:
                sections.append((start, end))
                current = line
            else:
                current = line
            start = end
        end += 1
        
    # todo: throw out sections with bad ratios of bad match options.
    # atm, if it's positional, check if it's in usage, if not, throw it out.
    options = []
    # print([o.switch.groups()[0] for o in usage.options])
    for start, end in sections:
        _, _, out_options = parse_help(text, start, end)
        for option in out_options:
            if option.is_positional:
                # print(option.switch.groups())
                if option.switch.groups()[0] in [o.switch.groups()[0] for o in usage.options]:
                    # print("adding positional!")
                    options.append(option)
                else:
                    # print("failed to add '"+option.switch.groups()[0]+"' it's not in usage.")
                    pass
            else:
                options.append(option)
            pass
    
    
    return usage, options

def parse_usage(text, start = 0):
    # Parse usage    
    usage = None
    argument = None
    line_num = start
    num_options = 0
    # Only checking the first 32 lines.
    for line in text[start:32]:
        line_num += 1
        pos = 0
        if not usage and (not (match := reg.usage.search(line[pos:]))):
            continue
        if match or (usage and len(line)-len(line.lstrip()) >= usage.match.span()[1]
              and usage.lines[-1][0] == line_num -1):

            if not usage:
                usage = Usage()
                usage.match = match
            else:
                match = usage.match

            usage.lines.append((line_num, line))

            while(line[pos:]):
                if match:
                    pos += match.span()[1]
                    usage.matches.append(match)
                
                # Handle options and arguments
                if match := reg.switch.search(line[pos:]):
                    option, pos = parse_option(line, pos, line_num, match)
                    option.doc = None
                    usage.options.append(option)
                    match = None
                    
                elif match := reg.argument.search(line[pos:]):
                    option, pos = parse_option(line, pos, line_num, match)
                    option.doc = None
                    usage.options.append(option)
                    match = None

                # Handle outer brackets
                elif match := reg.start_optional.search(line[pos:]): pass
                elif match := reg.end_optional.search(line[pos:]): pass
                elif match := reg.start_enum.search(line[pos:]): pass
                elif match := reg.end_enum.search(line[pos:]): pass
                
                # Handle syntactic sugar
                elif match := reg.ellipsis.search(line[pos:]): pass
                elif match := reg.comma.search(line[pos:]): pass
                elif match := reg.or_.search(line[pos:]): pass
                else:
                    if line[pos:]:
                        print("premature break: "+line[pos:])
                    break
        else:
            break

    if not usage:
        line_num = 0
    else:
        line_num -= 1

    cmd = []
    
    for option in usage.options:
        # print(option.switch.groups()[0]+" "+str(option.option_depth))
        # print(option.is_positional)
        if option.is_positional and option.option_depth == 0:
            cmd.append(option)
            pass
        else:
            break
    # print(cmd)
    usage.options = [o for o in usage.options if o not in cmd]
    cmd = [usage.match, *[o.switch for o in cmd]]
    usage.cmd = [o.groups()[0] for o in cmd]
    # print(usage.cmd)
    return usage, start, line_num

def parse_help(text, start=0, end=0, iterative=False):
    # Parse Options
    option = None
    prologue = []
    unused = []
    options = []
    # hack, stops us blocking legitimate names found in usage.
    Option.all_names = {}
    line_num = start
    end = len(text) if end == 0 else end
    
    for line in text[start:end]:
        line_num += 1
        pos = 0
        while(line[pos:]):

            if match := reg.has_arg.search(line[pos:]):
                # print(line)
                # print("starts: "+str(match.span(1)[0]))
                pos = match.span(1)[0]
                
                if match := reg.switch.search(line[pos:]): pass
                elif match := reg.argument.search(line[pos:]): pass
                if match:
                    # Not finding docs is a bad sign.
                    if option and not option.doc:
                        option.bad_match = True
                        option.bad_match_reason = "Couldn't find a doc string."

                    option, pos = parse_option(line, pos, line_num, match)
                    options.append(option)

                    if not option.bad_match:
                        pos = len(line)
                    elif not iterative:
                        pos = len(line)
                else:
                    print("Oh no! this is bad.")
                    print(line[pos:])
                        
                    
            elif option and reg.whitespace.search(line):
                # check if text starts past switch text
                pos = len(line) - len(line.lstrip())
                if pos > option.span[0]:
                    pos = len(line)
                    option.lines.append((line_num, line))
                    stripped = line.strip()
                    if stripped:
                        option.doc.append(stripped)
                else:
                    pos = len(line)
                    option = None
                    unused.append(line)    

            elif not options:
                pos = len(line)
                prologue.append(line)
                
            else:
                pos = len(line)
                option = None
                unused.append(line)
    
    return prologue, unused, options

def options_str_list(options, tab = 4, length = 64):
    lines = [",".join([o.name, *[c.name for c in o.children]]) for o in options]
    lines = [a+"," if a != lines[-1] else a for a in lines]
    lines = "".join(lines).split(",")
    lines = [a+", " if a != lines[-1] else a for a in lines]
    options_str = ""
    option_lines = []
    for d in lines:
        if len(options_str+d) > length:
            option_lines.append(options_str)
            options_str = d
        else:
            options_str += d
    if options_str:
        option_lines.append(options_str)
    return option_lines


def main():
    parser = argparse.ArgumentParser(prog=program_name, description=description)
    parser.add_argument("command", help="the command to convert to a module")
    parser.add_argument("--globals", "-g", action="append", help="flags to set globally for the module")
    parser.add_argument("-nb", "--no_bad_matches", action="store_true", help="don't display bad matches.")
    parser.add_argument("--verbose", action="store_true", help="show unused text etc.")
    parser.add_argument("-v", "--version", action="version", version=version)
    parser.add_argument("--debug", action="store_true", help="print debug information, don't build modules")
    # Tests
    # todo: make these self verifying.
    parser.add_argument("-t1", "--test1", help="test: default argparse arg for test")
    parser.add_argument("-t2", "--test2", nargs=3, metavar=("1st","2nd", "3rd"), help="test: nargs should be 3")
    parser.add_argument("-t3", "--test3", nargs="+", help="test: nargs should be +")
    parser.add_argument("-t4", "--test4", nargs="*", help="test: nargs should be *")
    parser.add_argument("-t5", "--test5", nargs="?", help="test: nargs should be ?")
    parser.add_argument("-t6", "--test6", nargs="...", help="test: nargs should be ...")
    parser.add_argument("-t7", "--test7", nargs="A...", help="test: nargs should be A...")
    parser.add_argument("-t8", "--test8", choices=["1st", "2nd", "3rd"], help="test: there should be 3 choices")
    
    args = parser.parse_args()
    help_text = subprocess.getoutput(args.command+" --help").split("\n")

    is_man_page = "NAME" in help_text and "SYNOPSIS" in help_text
    if args.debug:
        if  is_man_page:
            usage, options = parse_man(help_text)
            debug_print([], [], options, usage, "man", args.verbose, args.no_bad_matches)
            open(os.path.join(clpydir, "debug_help.txt"), "w").write("\n".join(help_text))
        else:
            usage, _, start = parse_usage(help_text)
            prologue, unused, options = parse_help(help_text, start=start)
            debug_print(prologue, unused, options, usage, "help", args.verbose, args.no_bad_matches)
            open(os.path.join(clpydir, "debug_help.txt"), "w").write("\n".join(help_text))
    else:
        if is_man_page:
            usage, options = parse_man(help_text)
            generate_module(usage, options, args.globals)
        else:
            usage, _, start = parse_usage(help_text)
            _, _, options = parse_help(help_text, start=start)
            generate_module(usage, options, args.globals)
        update_cli()

    
def generate_module(usage, options, defaults):
    # Filter out bad options etc.
    positional = [o for o in options if not o.bad_match and o.is_positional]
    options = [o for o in options if not o.bad_match and not o.is_positional]
    options_dict = {}
    for o in options:
        if o.name not in options_dict:
            options_dict[o.name] = o
    options = [o for o in options_dict.values()]
    option_dict = {}
    for o in options: option_dict = {**o.to_dict(), **option_dict}

    # Generate options.pkl
    cmd = "_".join(usage.cmd)
    usage_cmd = usage.cmd
    pickle.dump(option_dict, open(os.path.join(clpydir,f"{cmd}_options.pkl"), "wb"))


    length = 64
    tab = 4
    
    usage = ("\n").join(["".ljust(tab)+u[1] for u in [*usage.lines, (None,"")]])+"\n"
    
    docargs = options_str_list(positional, tab, length)
    if docargs:
        docargs = ["Positional arguments:",
                   "".ljust(length, "-"),
                    *docargs, "\n"]
        docargs = "".ljust(tab)+"\n".ljust(tab+1).join(docargs)
    else: docargs = ""

    docflags = options_str_list(options, tab, length)
    docflags2 = ""
    if docflags:
        docflags = ["All available flags:",
                    "".ljust(length, "-"),
                    *docflags, ""]
        docflags2 = docflags
        docflags = "".ljust(tab)+"\n".ljust(tab+1).join(docflags)
        docflags2 = "".ljust(tab*2)+"\n".ljust((tab*2)+1).join(docflags2)
    else: docflags = ""
    
    # Generate enums
    if docflags:
        enums = []
        enums.extend([
            (
                *["# "+d for d in o.doc],
                "# usage: func("+(f"(cli_{cmd}.{flag_name}.{o.name}, {o.nargs})" if o.nargs else f"cli_{cmd}.{flag_name}.{o.name}")+")",
                *[f"{d.name} = auto()" for d in [o, *[c for c in o.children if not c.bad_match]]]
            ) for o in options if o.is_parent
        ])
        enums = ["\n"+"\n".ljust(9).join(("", *a)) for a in enums]
        enums[0] = "".ljust(8)+enums[0].lstrip()
        enums = "".join(enums)
    else: enums = ""

    g_flags = defaults if defaults else []
    init = class_fmt.format(
        cmd=cmd,
        usage_cmd=usage_cmd,
        usage=usage,
        docflags=docflags,
        docargs=docargs,
        enum=enums,
        g_flags=g_flags,
        f=flag_name,
        docflags2=docflags2
    )
    open(os.path.join(clpydir, f"cli_{cmd}.py"), "w").write(init)

def update_cli():
    modules = os.listdir(clpydir)
    modules = [m[:-3] for m in modules if m.startswith("cli_") and m.endswith(".py")]
    modules = [f"from clpy.{m} import {m} as {m[4:]}" for m in modules]
    modules = sorted(modules)
    with open(os.path.join(clpydir, "cli.py"), "w") as cli_out:
        cli_out.write("\n".join(modules))
        pass
    
if __name__ == "__main__":
    main()

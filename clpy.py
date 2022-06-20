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
            if option.bad_match: out.append("bad_match:".ljust(just)+str(option.bad_match))
            if option.wants_equals: out.append("equals: ".ljust(just)+str(option.wants_equals))
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
    ellipsis = False
    wants_equals = False
    option_depth = 0
    enum_depth = 0

    def __init__(self):
        self.lines = []
        self.doc = []
        self.matches = []
        self.children = []
        self.arguments = []
        pass

    def to_dict(self):
        return {
            "switch": max([c.switch.group(1) for c in [self, *self.children]], key=len),
            "nargs": self.nargs,
            "wants_equals": self.wants_equals
        }

class Usage:
    match = None
    matches = None
    options = None
    positional = None
    lines = None

    def __init__(self):
        self.lines = []
        self.matches = []
        self.options = []
        self.positional = []

        
        
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
            break

    option_add_nargs(child)
    # todo: this is a hack to fix cases switch usage isn't explained in the parent.
    # it would probably be better to split each child into it's own long+short option
    # when creating modules.
    for child in option.children:
        if child.nargs and not option.nargs:
            option.nargs = child.nargs
        if child.wants_equals and not option.wants_equals:
            option.wants_equals = child.wants_equals

    opt_usage, doc = line[option.span[0]:pos], line[pos:]
    if doc.strip(): option.doc.append(doc.strip())
    option.usage = opt_usage.strip()
    option.name = max([c.switch.group(1).lstrip('-') for c in [option, *option.children]], key=len)
    option.name = option.name.replace("-", "_")
    if option.name in keyword.kwlist: option.name = option.name+"_"
    if option.name in dir(builtins): option.name = option.name+"_"
    return option, pos

def parse(text, iterative=False):
    
    # Parse usage    
    usage = None
    line_num = 0
    argument = None
    
    # Only checking the first 32 lines.
    for line in text[:32]:
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
                    usage.positional.append(match)

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

    # Parse Options
    option = None
    prologue = []
    unused = []
    options = []
    
    for line in text[line_num:]:
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
                    option.lines.append([line_num, line])
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
    
    return prologue, unused, options, usage


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
    # man_text = subprocess.getoutput("man -P cat "+args.command).split("\n")
    # todo: It might be better to have a base class + kwargs
    class_fmt = """# clpy generated, do not modify by hand
import subprocess
import pickle
import os
from enum import Enum, auto

curdir = os.path.dirname(__file__)
options = pickle.load(open(os.path.join(curdir, "options.pkl"), "rb"))

class cli_{cmd}:
    \"\"\"
    Functions are passed cli_{cmd}._.flags.
    Look at cli_{cmd}._ for more information.

    All available flags:
    -------------------
{doc}

    \"\"\"
    __g_flags = {g_flags}
    __flags = None
    def __init__(self, *in_flags):
        self.__flags = dict()
        self.add_flags(*in_flags)
        pass

    def add_flags(self, *in_flags):
        for a in in_flags:
            if isinstance(a, cli_{cmd}._):
                self.__flags[a] = a
            elif isinstance(a, tuple) and isinstance(a[0], cli_{cmd}._):
                self.__flags[a[0]] = a[1:]
        pass

    def del_flags(self, *in_flags):
        for a in in_flags:
            if a in self.__flags:
                del(self.__flags[a])
        pass

    def run(self, *in_args):
        args = ["{cmd}"]
        args.extend(self.__g_flags)
        for k in self.__flags:
            val = self.__flags[k]
            if isinstance(val, tuple):
                join = "=" if options[k.name]["wants_equals"] else " "
                args.append(options[k.name]["switch"]+join+",".join(val))
            else:
                args.append(options[k.name]["switch"])

        args.extend(in_args)
        print("Running: '"+" ".join(args)+"'")
        subprocess.run(args)
        pass

    class _(Enum):
{enum}
        pass
    """

    parsed = [(*parse(help_text), "help")]# , (*parse(man_text), "man")]
    for prologue, unused, options, usage, name in parsed:
        if args.debug:
            debug_print(prologue, unused, options, usage, name, args.verbose, args.no_bad_matches)
        else:
        
            # Filter out bad options etc.
            options = [o for o in options if not o.bad_match and not o.name.rstrip("_") in ["help", "version"]]
            # options = [o for o in options if len(o.name) > 2]
            options_dict = {}
            for o in options:
                if o.name not in options_dict:
                    options_dict[o.name] = o
            options = [o for o in options_dict.values()]
            option_dict = {o.name: o.to_dict() for o in options}

            # Generate options.pkl
            cmd = usage.match.groups()[0]
            os.makedirs(f"cli_{cmd}", exist_ok=True)
            pickle.dump(option_dict, open(f"cli_{cmd}/options.pkl", "wb"))

            # Generate docs
            # tab = 4
            # max_name = max([len(f"{cmd}._."+o.name+":  ") for o in options])+tab
            # doc = []
            # doc.extend(["".rjust(tab)+(f"({cmd}._.{o.name}, {o.nargs}): " if o.nargs else f"{cmd}._.{o.name}: ") for o in options])
            # doc = zip(doc, options)
            # doc = [n.ljust(max_name)+"\n".ljust(max_name+1).join(o.doc) for n, o in doc]
            # doc  = "\n".join(doc)+"\n"
            split = 5
            doc = []
            doc.extend([f"{o.name}" for o in options])
            doc = [a+", " if a != doc[-1] else a for a in doc]
            doc = [doc[a]+"\n".ljust(5) if a%split == split-1 else doc[a] for a in range(0, len(doc))]
            doc = "".ljust(4)+"".join(doc)
            

            # Generate props
            # split = 4
            # props = []
            # props.extend([f"{o.name}" for o in options if o.nargs])
            # props = [a+"=" for a in props]
            # props = [props[a]+"None\n"+"".ljust(4) if a%split == split-1 else props[a] for a in range(0, len(props))]
            # props.append("None" if len(props)%split != 0 else "")
            # props = "".ljust(4)+"".join(props)

            # Generate enums
            enums = []
            enums.extend([
                (
                    *["# "+d for d in o.doc],
                    "# usage: func("+(f"(cli_{cmd}._.{o.name}, {o.nargs})" if o.nargs else f"cli_{cmd}._.{o.name}")+")",
                    f"{o.name} = auto()"
                ) for o in options
            ])
            enums = ["\n"+"\n".ljust(9).join(("", *a)) for a in enums]
            enums[0] = "".ljust(8)+enums[0].lstrip()
            enums = "".join(enums)

            # Generate init args
            # args = []
            # args.extend([f"{o.name} = None" for o in options if o.nargs])
            # args = [a+", " if a != args[-1] else a for a in args]
            # args = [args[a]+"\n".ljust(18) if a%split == split-1 else args[a] for a in range(0, len(args))]
            # args = "".ljust(18)+"".join(args)
            #
            g_flags = args.globals if args.globals else []
            init = class_fmt.format(cmd=cmd, doc=doc, enum=enums, g_flags=g_flags)
            open(f"cli_{cmd}/__init__.py", "w").write(init)
            from cli_ls import cli_ls as ls
            ls(ls._.color).run()
            ls((ls._.width, "0")).run()


if __name__ == "__main__":
    main()

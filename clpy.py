#!/usr/bin/env python
import argparse
import subprocess
import re

program_name = "clpy"
description = """Convert a CLI to a python module."""
version = "0.0.1"

class reg:
    whitespace = re.compile("^\s")
    ellipsis = re.compile("^ ?\.\.\.")
    start_optional = re.compile("^ ?\[")
    end_optional = re.compile("^ ?\]")
    start_enum = re.compile("^ ?\{")
    end_enum = re.compile("^ ?\}")
    switch = re.compile("^(?:\s+)?(--?(?!-)[A-Za-z0-9\-#]+)")
    argument = re.compile("^(?: |=)?((?!-)[A-Za-z0-9\-<>#_]+)")
    equals = re.compile("^(=|\[=)")
    comma = re.compile("^, ?")
    or_ = re.compile("^\| ?")
    stop = re.compile("^\s\s")

class OptionMeta:
    def str(option):
        out = []
        just = 16
        if option.lines:
            out.append("["+"".ljust(64,'-')+"]")
            name = max([option.switch.groups()[0], *[c.switch.groups()[0] for c in option.children]], key=len)
            name = " "+name.strip('-')+" "
            out.append("["+name.center(64,'-')+"]")
            out.append("["+"".ljust(64,'-')+"]")
            out.append("original line/s:")
            out.append("'"+"'\n'".join(option.lines)+"'\n")
        if option.usage:
            out.append("usage:".ljust(just)+option.usage)
            out.append("bad_match:".ljust(just)+str(option.bad_match))
            out.append("equals: ".ljust(just)+str(option.wants_equals))
        if option.switch:
            out.append("switch:".ljust(just)+str(option.switch.groups()[0]))
        if option.nargs:
            out.append("nargs:".ljust(just)+str(option.nargs))
        if option.arguments:
            out.append("arguments:".ljust(just)+", ".join([f.tostr() for f in option.arguments]))
        if option.children:
            out.append("["+"children".center(64,'-')+"]")
            out.extend([OptionMeta.str(c) for c in option.children])
        if option.doc:
            tab = "".ljust(just, " ")
            out.append("docs:".ljust(just)+("\n"+tab).join(option.doc))
        else:
            out.append("["+"".ljust(64,'-')+"]")
        return "\n".join(out)

class Argument:
    is_optional = False # else is positional
    wants_equals = False
    default = None
    choices = None
    def tostr(self):
        out = ", ".join([m.groups()[0] for m in self.choices])
        if len(self.choices) > 1:
            out = "{"+out+"}"
        if self.is_optional:
            out = f"[{out}]"
        return out
            
    def __init__(self, match, is_optional = False, wants_equals = False):
        self.wants_equals = wants_equals
        self.is_optional = is_optional
        self.match = match
        self.choices = [match]
    
class Option:
    lines = None
    doc = None
    usage = None
    arguments = None
    matches = None
    nargs = None
    switch = None
    children = None
    bad_match = False
    ellipsis = False
    wants_equals = False
    option_depth = 0
    enum_depth = 0

    def __init__(self):
        self.lines = []
        self.doc = []
        self.switch = ""
        self.matches = []
        self.children = []
        self.arguments = []



def parse(text, iterative=False):
    option = None
    header = []
    unused = []
    options = []
    line_num = 0
    for line in text:
        line_num += 1
        pos = 0
        while(line[pos:]):
            if match := reg.switch.search(line[pos:]):
                start_pos = pos+match.span()[1]
                if option and not option.doc:
                    # Not finding docs is a bad sign.
                    option.bad_match = True
                option = Option()
                options.append(option)
                option.lines.append(line)
                option.switch = match
                child = option
                argument = None
                
                def add_nargs(child):
                    if child.arguments:
                        if not any([a.is_optional for a in child.arguments]) and not child.ellipsis:
                            child.nargs = str(len(child.arguments))
                        elif len(child.arguments) == 1 and child.arguments[0].is_optional and not child.ellipsis:
                            child.nargs = "?"
                        elif all([a.is_optional for a in child.arguments]) and child.ellipsis:
                            child.nargs = "*"
                        elif not child.arguments[0].is_optional and all([a.is_optional for a in child.arguments[1:]]) and child.ellipsis:
                            child.nargs = "+"
                        elif all([not a.is_optional for a in child.arguments]) and child.ellipsis:
                            child.nargs = "A..."
                    elif child.ellipsis:
                        child.nargs = "..."

                # Start searching for options etc.
                while(match):
                    child.matches.append(match)
                    pos += match.span()[1]
                    if not line[pos:]: break
                    
                    # Handle arguments
                    if match := reg.argument.search(line[pos:]):

                        if wants_equals := bool(reg.equals.search(line[pos:])):
                            child.wants_equals = True

                        if argument and child.enum_depth != 0:
                            argument.choices.append(match)
                        else:
                            argument = Argument(match, wants_equals=wants_equals, is_optional=child.option_depth !=0 )
                            child.arguments.append(argument)
                            argument = argument if child.enum_depth != 0 else None
                    
                    # Handle child options
                    elif match := reg.switch.search(line[pos:]):
                        add_nargs(child)
                        child = Option()
                        option.children.append(child)
                        child.switch = match

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
                        pos = start_pos
                        option.bad_match = True
                        break
                    
                add_nargs(child)
                usage, doc = line[:pos], line[pos:]
                if doc.strip(): option.doc.append(doc.strip())
                option.usage = usage.strip()
                if not option.bad_match:
                    pos = len(line)
                elif not iterative:
                    pos = len(line)
                    
            elif option and reg.whitespace.search(line):
                pos = len(line)
                option.lines.append(line)
                stripped = line.strip()
                if stripped:
                    option.doc.append(stripped)

            elif not options:
                pos = len(line)
                header.append(line)
                
            else:
                pos = len(line)
                option = None
                unused.append(line)
                
    return header, unused, options
        
def main():
    parser = argparse.ArgumentParser(prog=program_name, description=description)
    parser.add_argument("command", help="the command to convert to a module")
    parser.add_argument("-v", "--version", action="version", version=version)
    parser.add_argument("-t1", "--test1", help="complex arg for testing")
    parser.add_argument("-t2", "--test2", nargs=3, metavar=("1st","2nd", "3rd"), help="complex arg for testing")
    parser.add_argument("-t3", "--test3", nargs="+", help="complex arg for testing")
    parser.add_argument("-t4", "--test4", nargs="*", help="complex arg for testing")
    parser.add_argument("-t5", "--test5", nargs="?", help="complex arg for testing")
    parser.add_argument("-t6", "--test6", nargs="...", help="complex arg for testing")
    parser.add_argument("-t7", "--test7", nargs="A...", help="complex arg for testing")
    parser.add_argument("-t8", "--test8", choices=["1st", "2nd", "3rd"], help="complex arg for testing")
    
    args = parser.parse_args()
    help_text = subprocess.getoutput(args.command+" --help").split("\n")
    man_text = subprocess.getoutput("man -P cat "+args.command).split("\n")

    parsed = [(*parse(help_text), "help"), (*parse(man_text), "man")]
    for header, unused, options, name in parsed:
        print("".ljust(128, "="))
        print(f" {name} ".center(128, "="))
        print("".ljust(128, "="))
        print("\n".join(header))
        print("")
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
        print("\n".join(unused))

if __name__ == "__main__":
    main()

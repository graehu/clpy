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
    switch = re.compile("^(?:\s+)?--?(?!-)([A-Za-z0-9\-]+)")
    argument = re.compile("^(?: |=)?((?!-)[A-Za-z0-9\-<>#_]+)")
    equals = re.compile("^(=|\[=)")
    comma = re.compile("^, ?")
    stop = re.compile("^\s\s")

class OptionMeta:
    def str(option):
        out = []
        just = 16
        if option.lines:
            out.append("original line/s:")
            out.append("'"+"'\n'".join(option.lines)+"'\n")
        if option.usage:
            out.append("usage:".ljust(just)+option.usage)
            out.append("bad_match:".ljust(just)+str(option.bad_match))
            out.append("equals: ".ljust(just)+str(option.wants_equals))
        if option.switches:
            out.append("switch:".ljust(just)+str([f.groups() for f in option.switches]))
        if option.positional:
            out.append("positional:".ljust(just)+str([f.groups() for f in option.positional]))
        if option.optional:
            out.append("optional:".ljust(just)+str([f.groups() for f in option.optional]))
        tab = "".ljust(just, " ")
        if option.doc:
            out.append("docs:".ljust(just)+("\n"+tab).join(option.doc))
        if out:
            out.append("}"+"".ljust(64, '-')+"{")
        return "\n".join(out)
        

class Option:
    lines = None
    doc = None
    usage = None
    matches = None
    positional = None
    switches = None
    optional = None
    bad_match = False
    wants_equals = False
    depth = 0

    def __init__(self):
        self.lines = []
        self.doc = []
        self.matches = []
        self.positional = []
        self.switches = []
        self.optional = []

def main():
    parser = argparse.ArgumentParser(prog=program_name, description=description)
    parser.add_argument("-v", "--version", action="version", version=version)
    parser.add_argument("-c", "--command", required=True, help="the command to convert to a module")
    parser.add_argument("-t1", "--test1", help="complex arg for testing")
    parser.add_argument("-t2", "--test2", nargs=3, help="complex arg for testing")
    parser.add_argument("-t3", "--test3", nargs="+", help="complex arg for testing")
    parser.add_argument("-t4", "--test4", nargs="*", help="complex arg for testing")
    parser.add_argument("-t5", "--test5", nargs=3, metavar=("1st","2nd", "3rd"), help="complex arg for testing")
    
    args = parser.parse_args()
    help_text = subprocess.getoutput(args.command+" --help").split("\n")
    option = None
    header = []
    unused = []
    options = []
    for line in help_text:
        match = reg.switch.search(line)
        if match:
            if option and not option.doc:
                # Something went wrong, no doc for the last line.
                option.bad_match = True
            option = Option()
            options.append(option)
            option.lines.append(line)
            option.switches.append(match)
            pos = 0
            while(match):
                option.matches.append(match)
                pos += match.span()[1]
                if not line[pos:]:
                    break
                last_match = match
                match = None
                match = reg.argument.search(line[pos:])
                if match:
                    if reg.equals.search(line[pos:]):
                        option.wants_equals = True
                    if option.depth == 0:
                        option.positional.append(match)
                    else:
                        option.optional.append(match)
                    continue
                match = reg.switch.search(line[pos:])
                if match:
                    option.switches.append(match)
                    continue
                match = reg.start_optional.search(line[pos:])
                if match:
                    option.depth += 1
                    continue
                match = reg.end_optional.search(line[pos:])
                if match:
                    option.depth -= 1
                    continue
                match = reg.ellipsis.search(line[pos:])
                if match:
                    continue
                match = reg.comma.search(line[pos:])
                if match:
                    continue
                match = reg.stop.search(line[pos:])
                if match:
                    pos += match.span()[1]
                    break
                # Something went wrong.
                # Reverting to last found switch.
                pos = option.switches[-1].span()[1]
                option.bad_match = True
                break
            usage, doc = line[:pos], line[pos:]
            if doc.strip(): option.doc.append(doc.strip())
            option.usage = usage.strip()
        elif option and reg.whitespace.search(line):
            option.lines.append(line)
            stripped = line.strip()
            if stripped:
                option.doc.append(stripped)
        elif not options:
            header.append(line)
        else:
            option = None
            unused.append(line)

    print("\n".join(header))
    print("----------------")
    print("bad matches:")
    print("----------------")
    for o in options:
        if o.bad_match:
            print(OptionMeta.str(o))
    print("----------------")
    print("good matches:")
    print("----------------")
    for o in options:
        if not o.bad_match:
            print(OptionMeta.str(o))
    print("----------------")
    print("\n".join(unused))

if __name__ == "__main__":
    main()

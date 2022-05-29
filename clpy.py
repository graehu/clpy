#!/usr/bin/env python
import argparse
import subprocess
import re

program_name="clpy"
description="""Convert a CLI to a python module."""
version="0.0.1"
class reg:
    whitespace = re.compile("^\s")
    word = re.compile("[A-Za-z0-9]+")
    optional = re.compile("\[=?([A-Za-z0-9]+)\]")
    # arg = re.compile("^\s+-(?:-)?([A-Za-z0-9\-]+)(?:\[?(=| )\[?([A-Za-z0-9\-<>]+)\]?(?:, |\s\s))?")
    arg = re.compile("^\s+--?([A-Za-z0-9\-]+)" + # --switch
                     "(?:\[?(=| )\[?([A-Za-z0-9\-<>]+)\]?" + #[=<optional>]
                     ", |\s\s)?") # ensure ending whitespace
    long_arg = re.compile("--([A-Za-z0-9\-]+)(?:(=| )([A-Za-z0-9\-<>]+))?")

class OptionMeta:
    def str(option):
        out = []
        
        # todo: do rjusts on on titles instead of manual spaces
        if option.lines:
            out.append("'"+"'\n'".join(option.lines)+"'\n")
        if option.opts:
            out.append("options: "+option.opts)
        if option.short_opt:
            out.append("short:   "+str(option.short_opt.groups()))
        if option.long_opt:
            out.append("long:    "+str(option.long_opt.groups()))
        tab = "".ljust(len("docs:    "), " ")
        if option.doc:
            out.append("docs:    "+("\n"+tab).join(option.doc))
        if out:
            out.append("}"+"".ljust(64, '-')+"{")
        return "\n".join(out)
        

class Option:
    lines = None
    opts = None
    short_opt = None
    long_opt = None
    doc = None
    def __init__(self):
        self.doc = []
        self.lines = []

def main():
    parser = argparse.ArgumentParser(prog=program_name, description=description)
    parser.add_argument("-v", "--version", action="version", version=version)
    parser.add_argument("-c", "--command", required=True, help="the command to convert to a module")
    parser.add_argument("-t1", "--test1", help="complex arg for testing")
    parser.add_argument("-t2", "--test2", nargs=3, help="complex arg for testing")
    parser.add_argument("-t3", "--test3", nargs="+",help="complex arg for testing")
    parser.add_argument("-t4", "--test4", nargs="*",help="complex arg for testing")
    args = parser.parse_args()
    help_text = subprocess.getoutput(args.command+" --help").split("\n")
    cur_option = None
    header = []
    unused = []
    options = []
    for line in help_text:
        match = reg.arg.search(line)
        if match and reg.word.search(match.group(1)):
            cur_option = Option()
            options.append(cur_option)
            cur_option.lines.append(line)
            cur_option.short_opt = match
            pos = match.span()[1]
            match = reg.long_arg.search(line, pos)
            cur_option.long_opt = match
            if match:
                pos = match.span()[1]
            opts, doc = line[:pos], line[pos:]
            if doc.strip():
                cur_option.doc.append(doc.strip())
            cur_option.opts = opts.strip()
        elif cur_option and reg.whitespace.search(line):
            cur_option.lines.append(line)
            stripped = line.strip()
            if stripped:
                cur_option.doc.append(stripped)
        elif not options:
            header.append(line)
        else:
            # Note: This is potentially dangerous.
            cur_option = None
            unused.append(line)

    print("\n".join(header))
    print("----------------")
    for o in options:
        print(OptionMeta.str(o))
    print("----------------")
    print("\n".join(unused))

if __name__ == "__main__":
    main()

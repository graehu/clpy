#!/usr/bin/env python
import argparse
import subprocess
import re

program_name="clpy"
description="""Convert a CLI to a python module."""
version="0.0.1"
whitespace = re.compile("^\s")
option = re.compile("--([A-Za-z0-9\-]+)(?:\s+)?(.*?\n)")
short_option = re.compile("^\s+-([A-Za-z0-9]+)(?:(=| )([A-Za-z0-9]+))?")
long_option = re.compile("(?:^\s+|, )--([A-Za-z0-9\-]+)(?:(=| )([A-Za-z0-9\-]+))?")

class OptionMeta:
    def str(option):
        out = []
        # todo: do rjusts on on titles instead of manual spaces
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
            out.append("---")
        return "\n".join(out)
        

class Option:
    opts = None
    short_opt = None
    long_opt = None
    doc = None
    def __init__(self):
        self.doc = []

def main():
    parser = argparse.ArgumentParser(prog=program_name, description=description)
    parser.add_argument("-v", "--version", action="version", version=version)
    parser.add_argument("-c", "--command", required=True, help="the command to convert to a module")
    args = parser.parse_args()
    help_text = subprocess.getoutput(args.command+" --help").split("\n")
    cur_option = None
    for line in help_text:
        match = short_option.search(line)
        if match:
            if cur_option:
                print(OptionMeta.str(cur_option))
            cur_option = Option()
            cur_option.short_opt = match
            split_str = [x for x in match.groups() if x][-1]
            pos = match.span()[1]
            # print(line)
            # print("short: "+str(match.groups()))
            match = long_option.search(line)
            cur_option.long_opt = match
            if match:
                split_str = [x for x in match.groups() if x][-1]
                pos = match.span()[1]
                # print("long: "+str(match.groups()))
            # print("split: "+str(split_str))
            print(pos)
            opts, doc = line[:pos], line[pos:]

            # print("doc: "+doc.strip())
            if doc.strip():
                cur_option.doc.append(doc.strip())
            cur_option.opts = opts.strip()
        elif cur_option and whitespace.search(line):
            stripped = line.strip()
            if stripped:
                cur_option.doc.append(stripped)
    print(OptionMeta.str(cur_option))

if __name__ == "__main__":
    main()

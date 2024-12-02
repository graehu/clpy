# clpy

usage: clpy [-h] [-v] -c COMMAND

Convert a CLI to a python module.

### example
``` python
# python3 -m clpy ls
import clpy.ls as ls

print(ls.run(ls.flags.l).stdout)

# drwxrwxr-x 4 graehu graehu  4096 Dec  2 23:04 clpy
# -rw-rw-r-- 1 graehu graehu  1070 Nov 30 23:56 license.txt
# -rw-rw-r-- 1 graehu graehu   414 Dec  2 23:09 readme.md

```

optional arguments:
  -h, --help            show this help message and exit
  -v, --version         show program's version number and exit
  -c COMMAND, --command COMMAND
                        the command to convert to a module

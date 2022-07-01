import subprocess

silent = True

class cli:
    """
    base class for all cli modules.
    not for direct use.
    """
    __g_flags = []
    __flags = None
    __cmd = ["echo"]
    __options = None
    def __init__(self, cmd, options, g_flags, *in_flags):
        self.__cmd = cmd
        self.__options = options
        self.__g_flags = g_flags
        self.__flags = dict()
        self.add_flags(*in_flags)
        pass

    def add_flags(self, *in_flags):
        for a in in_flags:
            if isinstance(a, self.f):
                self.__flags[a] = a
            elif isinstance(a, tuple) and isinstance(a[0], self.f):
                if len(a) > 1:
                    self.__flags[a[0]] = a[1:]
                else:
                    self.__flags[a[0]] = a[0]
            elif not silent:
                print("Failed to add '"+str(a)+"', it's not a "+type(self).__name__+".f flag")
        pass

    def del_flags(self, *in_flags):
        for a in in_flags:
            if a in self.__flags:
                del(self.__flags[a])
        pass

    def run(self, *in_args):
        args = [*self.__cmd]
        args.extend(self.__g_flags)
        for k in self.__flags:
            val = self.__flags[k]
            if isinstance(val, tuple):
                val = [str(v) for v in val]
                join = "=" if self.__options[k.name]["wants_equals"] else " "
                args.append(self.__options[k.name]["switch"]+join+",".join(val))
            else:
                args.append(self.__options[k.name]["switch"])

        args.extend(in_args)
        if not silent:
            print("Running: '"+" ".join(args)+"'")

        try:
            return subprocess.run(args, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(e.stderr) from e


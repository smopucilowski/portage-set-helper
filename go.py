#!/usr/bin/env python3
from collections.abc import MutableSequence
from itertools import product
from pathlib import Path
from portage.dep import isvalidatom
import argparse
import portage

#______________________________________________________________________________
class PortageSet(MutableSequence):
    def __init__(self, path):
        self.path    = path
        self.entries = []

    def __repr__(self):
        return "PortageSet('%s (%d entries)')" % (self.path, len(self.entries))

    @property
    def name(self):
        return self.path.name

    def check(self):
        [e.check() for e in self.entries]

    def import_set(self):
        lines = enumerate(open(self.path, 'r').read().splitlines(), 1)
        for line_no, line in lines:
            if not line or line.lstrip()[0] == '#':
                self.entries.append(Comment(self.path, line, line_no))
            else:
                self.entries.append(EBuild(self.path, line, line_no))

    # abc methods
    def __delitem__(self, index):
        del self.entries[index]
    def __getitem__(self, index):
        return self.entries[index]
    def __setitem__(self, index, value):
        self.entries[index] = value
    def __len__(self):
        return len(self.entries)
    def insert(self, index, value):
        self.entries.insert(index, value)

class Entry():
    def __init__(self, path, line, line_no):
        self.path    = path
        self.line    = line
        self.line_no = line_no

    def __repr__(self):
        return "Entry('%s:%d')" % (self.path, self.line_no)

    def check(self):
        pass

class Comment(Entry):
    def __init__(self, path, line, line_no):
        super().__init__(path, line, line_no)

    def __repr__(self):
        return "Comment('%s:%d')" % (self.path, self.line_no)

    def check(self):
        return True

    def pretty_print(self, prefix, color=True):
        if color:
            return '%s\033[2m%s\033[0m' % (prefix, self.line)
        else:
            return '%s' % self.line

    def formatted(self, destination):
        return '%s' % self.line

class EBuild(Entry):
    def __init__(self, path, line, line_no):
        super().__init__(path, line, line_no)
        tokens = line.split()
        self.keyword = False
        self.skip    = False
        # Entries which start with a ! are keyworded
        if tokens[0] == '!':
            self.keyword = True
            tokens = tokens[1:]
        # Entries which start with a - set use flags, but not explicitly select the ebuild
        elif tokens[0] == '-':
            self.skip = True
            tokens = tokens[1:]
        else:
            self.keyword = False
        self.cpv  = tokens[0]
        # Sort USE flags in [use, +use, -use] order
        self.uses = tokens[1:]
        self.uses.sort()
        self.uses.sort(key=lambda x:x[0]=='+')
        self.uses.sort(key=lambda x:x[0]=='-')

    def __repr__(self):
        status = ''
        if self.keyword:
            status = '!'
        if self.skip:
            status = '-'
        return "EBuild('%s:%d:%s%s')" % (self.path, self.line_no, status, self.cpv)

    def check(self):
        if not isvalidatom(self.cpv):
            print('%s:%d: error: not a valid portage atom: %s' % (self.path.name, self.line_no, self.cpv))
            return False

        # https://www.funtoo.org/Portage_API
        p = portage.db[portage.root]["porttree"].dbapi
        resolved_ebuild = p.xmatch(origdep=self.cpv, level='bestmatch-visible')
        if not resolved_ebuild:
            print('%s:%d: error: portage atom not in any repo: %s' % (self.path.name, self.line_no, self.cpv))
            return False
            
        def filtered_use(uses):
            for use in uses:
                if use[0] in ('+', '-'):
                    yield use[1:]
                else:
                    yield use

        ebuild_uses  = set(filtered_use(p.aux_get(resolved_ebuild, ['IUSE'])[0].split()))
        given_uses   = set(filtered_use(self.uses))
            
        unknown_uses = given_uses - ebuild_uses
        if unknown_uses:
            print('%s:%d: error: "%s" not a valid use flag: %s' % (
                self.path.name, self.line_no, ' '.join(unknown_uses), self.line
            ))
            print('└─ available USE flags: %s' % ' '.join(ebuild_uses))
            return False
        return True

    def pretty_print(self, color=True):
        if color:
            pretty_cpv = '\033[32m%s\033[0m' % self.cpv
            pretty_uses = []
            for use in self.uses:
                if use[0] == '+':
                    use = '\033[34m%s\033[0m' % use
                elif use[0] == '-':
                    use = '\033[31m%s\033[0m' % use
                else:
                    use = '\033[97m%s\033[0m' % use
                pretty_uses.append(use)
            return '%s %s' % (pretty_cpv, ' '.join(pretty_uses))
        else:
            return '%s %s' % (self.cpv, ' '.join(self.uses))

    def formatted(self, destination):
        if destination == 'package.accept_keywords':
            if self.keyword:
                return self.cpv
            else:
                return '#%s' % self.cpv
        if destination == 'package.use':
            if self.uses:
                return '%s %s' % (self.cpv, ' '.join(self.uses))
            else:
                return '#%s' % self.cpv
        if destination == 'sets':
            if self.skip:
                return '#%s (skipped)' % self.cpv
            else:
                return self.cpv

#______________________________________________________________________________
def lookahead(iterable):
    it = iter(iterable)
    last_value = next(it)
    for value in it:
        yield last_value, True
        last_value = value
    yield last_value, False

#______________________________________________________________________________
def main():
    make_conf_path = Path(str(portage.root)) / Path(portage.MAKE_CONF_FILE)
    parser = argparse.ArgumentParser(description='', epilog='')
    parser.add_argument('-f', '--force',   help='Force overwriting of portage set files', action='store_true')
    parser.add_argument('-o', '--output',  help='Portage configuration path. Formatted sets files will be created by default within /etc/portage/{package.accept_keywords,package.use,sets}/ directories. (autodetected: %(default)s)', default=make_conf_path.parent, action='store', type=Path)
    parser.add_argument('-q', '--quiet',   help='Suppress output', action='store_true')
    parser.add_argument('-n', '--dry-run', help='Only print what would be done', action='store_true')
    parser.add_argument('--strict',        help='Fail on warnings (unknown ebuilds, unknown USE flags)', action='store_true')
    parser.add_argument('--no-color',      help='Disable color output', dest='color', default=True, action='store_false')
    parser.add_argument('sets',            help='Portage set helper definitions', nargs='+', type=Path)
    args = parser.parse_args()

    #args.output = Path('test')
    portage_sets = [
        PortageSet(path)
        for path in args.sets
    ]

    for portage_set in portage_sets:
        portage_set.import_set()
        portage_set.check()

    import pdb; pdb.set_trace()

    destinations = 'package.accept_keywords', 'package.use', 'sets'
    for destination, portage_set in product(destinations, portage_sets):
        path = Path.joinpath(args.output, destination, portage_set.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        print(path)
        with path.open('w') as outfile:
            for entry in portage_set:
                print(entry.formatted(destination), file=outfile)
                print(entry.pretty_print(''))

if __name__=="__main__":
    main()

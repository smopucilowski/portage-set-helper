#!/usr/bin/env python3
from itertools import product
from pathlib import Path
from portage.dep import isvalidatom
import argparse
import portage

#______________________________________________________________________________
class PortageSet()
    def __init__(self, path):
        self.path    = path
        self.entries = []

class Entry()
    def __init__(self, path, line_no, line):
        self.path    = path
        self.line_no = line_no
        self.line    = line

class Ebuild():
    def __init__(self, cpv, keyword, uses, path, line_no):
        self.cpv     = cpv
        self.keyword = keyword
        self.uses    = uses
        self.path    = path
        self.line_no = line_no

    def check(self):
        if not isvalidatom(self.cpv):
            print('%s:%d: error: not a valid portage atom: %s' % (self.path.name, self.line_no, self.cpv))
            return False

        actual_ebuild = portage.db[portage.root]["porttree"].dbapi.xmatch(
            origdep=self.cpv, level='bestmatch-visible'
        )
        if not actual_ebuild:
            print('%s:%d: error: portage atom not in any repo: %s' % (self.path.name, self.line_no, self.cpv))
            return False
            
        def filtered_use(uses):
            for use in uses:
                if use[0] in ('+', '-'):
                    yield use[1:]
                else:
                    yield use

        permitted_uses = set(filtered_use(
            portage.db[portage.root]["porttree"].dbapi.aux_get(actual_ebuild, ['IUSE'])[0].split()
        ))
        supplied_uses = set(filtered_use(self.uses))
            
        unknown_uses = supplied_uses - permitted_uses
        if unknown_uses:
            print('%s:%d: error: "%s" not a valid use flag: %s %s' % (
                self.path.name, self.line_no, 
                ' '.join(unknown_uses),
                self.cpv, ' '.join(self.uses))
            )
            print('└─ available USE flags: %s' % ' '.join(permitted_uses))
            return False
        return True

    def formatted(self, color):
        self.uses.sort()
        self.uses.sort(key=lambda x:x[0]=='+')
        self.uses.sort(key=lambda x:x[0]=='-')
        if color:
            cpv  = '\033[32m%s\033[0m' % self.cpv
            uses = []
            for use in self.uses:
                if use[0]=='+':
                    use = '\033[34m%s\033[0m' % use
                elif use[0]=='-':
                    use = '\033[31m%s\033[0m' % use
                else:
                    use = '\033[97m%s\033[0m' % use
                uses.append(use)
            return '%s %s' % (cpv, ' '.join(uses))
        else:
            return '%s %s' % (self.cpv, ' '.join(self.uses))

class Comment():
    def __init__(self, line, path, line_no):
        self.line    = line
        self.path    = path
        self.line_no = line_no

    def check(self):
        return True

    def formatted(self, color):
        if color:
            return '\033[2m%s\033[0m' % self.line
        else:
            return self.line

#______________________________________________________________________________
def lookahead(iterable):
    it = iter(iterable)
    last_value = next(it)
    for value in it:
        yield last_value, True
        last_value = value
    yield last_value, False

#______________________________________________________________________________
def pretty_print(portage_set, color):
    if color:
        print('\033[1m\033[97m@%s\033[0m (%s)' % (portage_set['name'], portage_set['path']))
    else:
        print('@%s (%s)' % (portage_set['name'], portage_set['path'].resolve()))

    for entry, has_more in lookahead(portage_set['entries']):
        if not has_more:
            print('└─', entry.formatted(color))
            continue
        if isinstance(entry, Comment):
            print('│ ', entry.formatted(color))
        else:
            print('├─', entry.formatted(color))

def import_portage_set(path, strict):
    lines = enumerate(open(path, 'r').read().splitlines(), 1)
    entries = []
    portage_set = {
        'name':     path.name,
        'path':     path,
        'lines':    lines,
        'entries':  entries,
    }
    for line_no, line in lines:
        tokens = line.split()
        # Skip empty lines and comments
        if not tokens or tokens[0][0] == '#':
            entries.append(Comment(
                line, path, line_no
            ))
            continue
        if tokens[0] == '!':
            keyword = True
            atom = tokens[1]
            uses = tokens[2:]
        else:
            keyword = False
            atom = tokens[0]
            uses = tokens[1:]
        ebuild = Ebuild(
            cpv=atom, keyword=keyword, uses=uses, path=path, line_no=line_no,
        )
        entries.append(ebuild)
    return portage_set

def go(args):
    try:
        portage_sets = [
            import_portage_set(path, args.strict)
            for path in args.sets
        ]
    except FileNotFoundError as e:
        print(e)
        exit(e.errno)
    except:
        raise

    checks = True
    for portage_set in portage_sets:
        if not all([e.check() for e in portage_set['entries']]):
            checks = False
    if args.strict and not checks:
        exit(1)

    if not args.quiet:
        for portage_set, has_more in lookahead(portage_sets):
            pretty_print(portage_set, args.color)
            if has_more: print('')

    if args.dry_run:
        exit(0)

    args.output = Path('dev')

    # Check if files already exist
    path_akw  = Path.joinpath(args.output, 'package.accept_keywords', portage_set['name'])
    path_pu   = Path.joinpath(args.output, 'package.use', portage_set['name'])
    path_sets = Path.joinpath(args.output, 'sets', portage_set['name'])
    import pdb; pdb.set_trace()
    if args.force:
        print('')
        for path, entry in product((path_akw, path_pu, path_sets), portage_sets):
            if path.exists():
                print('%s exists, aborting' % path.path)
                exit(1)
    exit(1)

    for portage_set in portage_sets:
        # package.accept_keywords
        path = Path.joinpath(args.output, 'package.accept_keywords', portage_set['name'])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w') as outfile:
            for entry in portage_set['entries']:
                if isinstance(entry, Comment):
                    print(entry.line, file=outfile)
                else:
                    if entry.keyword:
                        print(entry.cpv, file=outfile)
                    else:
                        print('#%s' % entry.cpv, file=outfile)

        path = Path.joinpath(args.output, 'package.use', portage_set['name'])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w') as outfile:
            for entry in portage_set['entries']:
                if isinstance(entry, Comment):
                    print(entry.line, file=outfile)
                else:
                    if entry.uses:
                        print(entry.formatted(color=False), file=outfile)
                    else:
                        print('#%s' % entry.formatted(color=False), file=outfile)

        path = Path.joinpath(args.output, 'sets', portage_set['name'])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w') as outfile:
            for entry in portage_set['entries']:
                if isinstance(entry, Comment):
                    print(entry.line, file=outfile)
                else:
                    print(entry.cpv, file=outfile)

def main():
    make_conf_path = Path(str(portage.root)) / Path(portage.MAKE_CONF_FILE)
    parser = argparse.ArgumentParser(description='', epilog='')
    parser.add_argument('-f', '--force',   help='Force overwriting of portage set files', action='store_true')
    parser.add_argument('-n', '--dry-run', help='Only print what would be done', action='store_true')
    parser.add_argument('-q', '--quiet',   help='Suppress output', action='store_true')
    parser.add_argument('-o', '--output',  help='Portage configuration path. Formatted sets files will be created by default within /etc/portage/{package.accept_keywords,package.use,sets}/ directories. (default: %(default)s)', default=make_conf_path.parent, action='store', type=str)
    parser.add_argument('--strict',        help='Fail on warnings (unknown ebuilds, USE flags)', action='store_true')
    parser.add_argument('--no-color',      help='Disable color output', dest='color', default=True, action='store_false')
    parser.add_argument('sets',            help='Portage set definitions', nargs='+', type=Path)
    args = parser.parse_args()
    go(args)

if __name__=="__main__":
    main()

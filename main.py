from gullian_parser.source import Source
from gullian_parser.lexer import Lexer
from gullian_parser.parser import Parser

from gullian_checker.checker import Module, Checker
from gullian_codegen.codegen_c import Codegen

module = Module.new()

hello_world = Source(open('examples/hello_world.gullian').read())
tokens = tuple(Lexer(hello_world, module.name).lex())
asts = tuple(Parser(Source(tokens), module.name).parse())

checker = Checker.new(module)

for checked in checker.check(asts):
    continue

codegen = Codegen(module)

output = open('out.c', 'w')
for code in codegen.gen():
    print(code)
    output.write(code)
    output.write('\n')
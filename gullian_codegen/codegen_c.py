from dataclasses import dataclass

from gullian_checker.module import Module, Type, GenericType, Function
from gullian_checker.checker import *

@dataclass
class Codegen:
    module: Module

    def gen_name(self, name: Name | Attribute):
        if type(name) is Attribute:
            return f'{self.gen_name(name.left)}_{self.gen_name(name.right)}'
        elif type(name) is Name:
            return name.format.replace('_', '__')

        return name.format
    
    def gen_type_name(self, type_: Type):
        if not type_.fields:
            return self.gen_name(type_.name)

        generated_anonymous_name = "_".join(self.gen_name(field_type) for _, field_type in type_.fields)

        return f'{self.gen_name(type_.name)}_{generated_anonymous_name}'

    def gen_type(self, type_: Type):
        generated_fields = "; ".join(f'{self.gen_name(field_type)} {self.gen_name(field_name)}' for field_name, field_type in type_.declaration.fields)
        generated_anonymous_name = "_".join(self.gen_name(field_type) for _, field_type in type_.fields)

        if type(type_.declaration) is StructDeclaration:
            return f'typedef struct '
        
        generated_functions = []

        for function in type_.functions.values():
            if type(function) is not GenericFunction:
                generated_functions.append(self.gen_function(function))
        
        for function in type_.anonymous_functions.values():
            generated_functions.append(self.gen_function(function))
        
        generated_enum_fields = ", ".join(f'{self.gen_name(type_.name)}_{generated_anonymous_name}__{self.gen_name(field_name)}' for field_name, _ in type_.declaration.fields)
        
        return '\n'.join([
            f'typedef enum {{ {generated_enum_fields} }} {self.gen_name(type_.name)}_{generated_anonymous_name}__FIELDS;',
            f'typedef struct {{ int tag; union {{ {generated_fields}; }}; }} {self.gen_name(type_.name)}_{generated_anonymous_name};\n' + '\n'.join(generated_functions)
        ])

    def gen_literal(self, literal: Literal):
        if type(literal.ast.value) is str:
            A, B = '"', '\\"'
            return f'"{literal.ast.value.replace(A, B)}"'
        
        return literal.format

    def gen_checked_call(self, checked_call: CheckedCall):
        generated_arguments = ", ".join(self.gen_expression(argument) for argument in checked_call.call.arguments)
        
        if checked_call.call.generic:
            generated_generic_names = "_".join(self.gen_name(type_) for type_ in checked_call.call.generic)

            return f'{self.gen_name(checked_call.function.head.name)}_{generated_generic_names}({generated_arguments})'

        return f'{self.gen_name(checked_call.function.head.name)}({generated_arguments})'
    

    def gen_union_literal(self, union_literal: Typed):
        generated_arguments = ", ".join(self.gen_expression(argument) for argument in union_literal.ast.arguments)
        fields_dict = {field_type: field_name for field_name, field_type in union_literal.type.fields}
        
        field_name = fields_dict[union_literal.ast.arguments[0].type]

        return f'({self.gen_type_name(union_literal.type)}) {{ {self.gen_type_name(union_literal.type)}__{self.gen_name(field_name)}, .{self.gen_name(field_name)}={generated_arguments} }}'

    def gen_struct_literal(self, struct_literal: Typed):
        if type(struct_literal.type.declaration) is UnionDeclaration:
            return self.gen_union_literal(struct_literal)

        generated_arguments = ", ".join(self.gen_expression(argument) for argument in struct_literal.ast.arguments)
        generated_anonymous_name = "_".join(self.gen_name(field_type) for _, field_type in struct_literal.type.fields)

        return f'({self.gen_name(struct_literal.type.name)}_{generated_anonymous_name}) {{ {generated_arguments} }}'

    def gen_expression(self, expression: Expression):
        # TODO: This is a provisory bugfix, fix later
        if type(expression) is Name:
            return expression.format
        # Also a bug
        elif type(expression) is Attribute:
            return f'{self.gen_expression(expression.left)}.{self.gen_expression(expression.right)}'
        
        if type(expression.ast) is Name:
            return expression.ast.format
        elif type(expression.ast) is Attribute:
            return f'{self.gen_expression(expression.ast.left)}.{self.gen_expression(expression.ast.right)}'
        if type(expression.ast) is Literal:
            return self.gen_literal(expression)
        elif type(expression.ast) is CheckedCall:
            return self.gen_checked_call(expression.ast)
        elif type(expression.ast) is StructLiteral:
            return self.gen_struct_literal(expression)
        elif type(expression.ast) is BinaryOperator:
            return f'{self.gen_expression(expression.ast.left)} {expression.ast.operator.format} {self.gen_expression(expression.ast.right)}'
        elif type(expression.ast) is UnaryOperator:
            return f'{expression.ast.operator.format}{self.gen_expression(expression.ast.expression)}'
        elif type(expression.ast) is TestGuard:
            return f'{self.gen_expression(expression.ast.expression.ast.left)}.tag == {self.gen_type_name(expression.ast.expression.ast.left.type)}__{expression.ast.expression.ast.right.format}'

        raise NotImplementedError(f'codegen_c(bug): generation for {expression.format} is not implemented yet')

    def gen_variable_declaration(self, variable_declaration: VariableDeclaration):
        return f'{self.gen_type_name(variable_declaration.hint)} {self.gen_name(variable_declaration.name)} = {self.gen_expression(variable_declaration.value)};'
    
    def gen_return(self, return_: Return):
        return f'return {self.gen_expression(return_.value)};'
    
    def gen_if(self, if_: If, indent=0):
        return f'if ({self.gen_expression(if_.condition)}) {self.gen_body(if_.true_body, indent +1)}'

    def gen_body(self, body: Body, indent=0):
        TABINDENT = '\n' + ('  ' * indent)
        TABINDENTNEXT = '\n' + ('  ' * (indent +1))

        def gen_line(line: Typed):
            if type(line) is Typed:
                if type(line.ast) is CheckedCall:
                    return self.gen_checked_call(line.ast) + ';'

            if type(line) is VariableDeclaration:
                return self.gen_variable_declaration(line)
            elif type(line) is Return:
                return self.gen_return(line)
            elif type(line) is If:
                return self.gen_if(line, indent)

            return f'// {line.format}'

        return '{' + "".join(TABINDENTNEXT + gen_line(line) for line in body.lines) + TABINDENT + '}'

    def gen_function(self, function: Function):
        compiled_head_parameters = ", ".join(f"{self.gen_type_name(parameter_type)} {parameter_name.format}" for parameter_name, parameter_type in function.head.parameters)

        if type(function.declaration) is Extern:
            return f'// extern: {function.head.return_hint.format} {function.head.name.format}({compiled_head_parameters})'
        
        if function.head.generic:
            compiled_generic_name = "_".join(self.gen_name(type_.name) for type_ in function.head.generic)

            return f'{self.gen_type_name(function.head.return_hint)} {self.gen_name(function.head.name)}_{compiled_generic_name}({compiled_head_parameters}) {self.gen_body(function.declaration.body)}'

        return f'{self.gen_type_name(function.head.return_hint)} {self.gen_name(function.head.name)}({compiled_head_parameters}) {self.gen_body(function.declaration.body)}'

    def gen(self):
        already_generated = set()

        def filter_duplicates(line: str):
            if line.startswith('//'):
                return line
            
            if line in already_generated:
                return f'// warning: duplicated code ommited */'

            already_generated.add(line)

            return line

        if self.module.name == 'main':
            yield '#include <stdlib.h>'
            yield '#include <stdio.h>'
            yield '#include <string.h>'
            yield '#define str char*'

            for basic_type in BASIC_TYPES.values():
                for function in basic_type.functions.values():
                    if type(function) is not GenericFunction:
                        yield self.gen_function(function)

                for associated_function in basic_type.anonymous_functions.values():
                    yield self.gen_function(associated_function)

        for import_ in self.module.imports.values():
            for module_line in Codegen(import_).gen():
                yield filter_duplicates(module_line)

        for type_ in self.module.types.values():
            # If the type is generic we do not compile it, only its applied variants
            if type(type_) is not GenericType:
                yield filter_duplicates(self.gen_type(type_))
        
        for type_ in self.module.anonymous_types.values():
            yield filter_duplicates(self.gen_type(type_))
        
        for function in self.module.functions.values():
            yield self.gen_function(function)
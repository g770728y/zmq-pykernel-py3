from code import CommandCompiler

compiler = CommandCompiler()

local_vars = {}
code = "x=10"
compiled_code = compile(code, "<string>", "exec")
exec(compiled_code, local_vars)
print(local_vars["x"])

code = "print(x+100)"
compiled_code = compile(code, "<string>", "exec")
exec(compiled_code, local_vars)
# exec comp_code in self.user_ns, self.user_ns

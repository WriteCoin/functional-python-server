import ast
from WebAutomation.general_utils import *

def get_defined_objects(code):
    imported_names = set()

    def by_scope(source: str):
        defined_objects = {
            "variables": [],
            "functions": [],
            "classes": {}
        }
        try:
            # print(source)
            tree = ast.parse(source)
        except SyntaxError:
            return defined_objects
        # try:
        #     tree = ast.parse(source)
        # except SyntaxError as ex:
        #     print(source)
        #     raise ex
        walk = ast.walk(tree)
        for node in walk:
            if isinstance(node, ast.Import):
                imported_names.update([n.asname or n.name for n in node.names])
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    imported_names.update([node.module + '.' + (n.asname or n.name) for n in node.names])
                else:
                    imported_names.update([(n.asname or n.name) for n in node.names])
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Name)):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    defined_objects['variables'].append(node.id)
                elif isinstance(node, ast.FunctionDef):
                    defined_objects['functions'].append(node.name)
                elif isinstance(node, ast.ClassDef):
                    code_child_nodes = ""
                    for child_node in ast.iter_child_nodes(node):
                        code_child_node = ast.get_source_segment(code, child_node)
                        if not code_child_node is None:
                            code_child_nodes += (code_child_node + '\n')
                    # print(node.name)
                    defined_objects['classes'][node.name] = by_scope(code_child_nodes)
        return defined_objects

    def entity_filter(defined_objects):
        defined_objects['variables'] = [name for name in defined_objects['variables'] if name not in imported_names]
        defined_objects['functions'] = [name for name in defined_objects['functions'] if name not in imported_names]
        for name in defined_objects['classes'].keys():
            if name in imported_names:
                del defined_objects['classes'][name]
            else:
                defined_objects['classes'][name] = entity_filter(defined_objects['classes'][name])
        return defined_objects

    defined_objects = entity_filter(by_scope(code))

    return defined_objects

def defined_objects_get_info(defined_objects, entity, scope_prefix = ""):
    objects_info = {}
    def by_variable(name, var_obj):
        return {
            "name": name,
            "type": str(type(var_obj)),
            "doc": var_obj.__doc__,
            "value": str(var_obj)
        }

    def recursion(defined_objects, entity, scope_prefix):
        full_path = lambda name_obj: scope_prefix + name_obj
        for var_name in defined_objects['variables']:
            try:
                var_obj = getattr(entity, var_name)
            except AttributeError:
                continue
            objects_info[full_path(var_name)] = by_variable(var_name, var_obj)
        for func_name in defined_objects['functions']:
            try:
                func_obj = getattr(entity, func_name)
            except AttributeError:
                continue          
            if isinstance(func_obj, property):
                objects_info[full_path(func_name)] = by_variable(func_name, func_obj)
                continue
            args = inspect.getfullargspec(func_obj)
            ret_type = "None"
            if hasattr(func_obj, '__annotations__') and 'return' in func_obj.__annotations__:
                ret_type = func_obj.__annotations__['return']
            objects_info[full_path(func_name)] = {
                "name": func_obj.__name__,
                "args": args.args,
                "return_type": str(ret_type),
                "doc": func_obj.__doc__
            }
        for class_name in defined_objects['classes'].keys():
            # print(class_name)
            try:
                class_obj = getattr(entity, class_name)
            except AttributeError:
                continue
            recursion(defined_objects['classes'][class_name], class_obj, scope_prefix + class_name + '.')
            # objects_info[full_path(class_name)] = defined_objects_get_info(defined_objects['classes'][class_name], class_obj, scope_prefix + class_name + '.')
    recursion(defined_objects, entity, scope_prefix)
    return objects_info

def get_abs_path_to_module(module_like_python: str):
    module = importlib.import_module(module_like_python)
    s = str(module.__path__)
    path = s[s.find('[\'') + len('[\''):s.find('\']')]
    return path

def get_objects(abs_path_to_module, module_prefix: Optional[str], excluded_modules: list[str] = []):
    objects = {}
    module_prefix = module_prefix + '.' if not module_prefix is None else ""
    first_part_module = os.path.basename(abs_path_to_module)
    for params in os.walk(abs_path_to_module):
        path, dirs, files = params
        dirname_of_path = os.path.basename(path)
        if not dirname_of_path.startswith('__'):
            for file in files:
                if file.endswith('.py'):
                    module_name = os.path.splitext(file)[0]
                    module_path = os.path.join(path, file)
                    module_python_path = module_prefix + os.path.splitext(os.path.join(first_part_module, os.path.relpath(module_path, abs_path_to_module)).replace(os.path.sep, '.'))[0]
                    is_key_excludes = module_python_path in excluded_modules
                    is_starts_excludes = find(lambda excluded_module: module_python_path.startswith(excluded_module), excluded_modules)
                    print("Обработка модуля", module_python_path, "Модуль в исключаемых?", is_key_excludes, "Путь к модулю начинается с исключенного?", not is_starts_excludes is None)
                    if not (is_key_excludes or is_starts_excludes):
                        with open(module_path, 'r', encoding='utf-8') as fd:
                            code = fd.read()
                            defined_objects = get_defined_objects(code)
                            # log(defined_objects)
                            module = importlib.import_module(module_python_path)
                            objects_info = defined_objects_get_info(defined_objects, module)
                            objects[module_python_path] = objects_info
    return objects
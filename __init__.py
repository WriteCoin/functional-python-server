from WebAutomation.general_utils import *
import ast
import conf
import uuid
import json
import http.server
import socketserver
from urllib.parse import urlparse, parse_qs, unquote
from pprint import pprint

log_file = open('output.txt', 'w', encoding='utf-8')
def log(msg):
    pprint(msg, stream=log_file)

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

def find_entity(module_path_or_entity, path):
    if isinstance(module_path_or_entity, str):
        module = importlib.import_module(module_path_or_entity)

        next_entity = module
    else:
        next_entity = module_path_or_entity

    # print(next_entity)

    for next_path in path.split('.'):
        if next_path.endswith('()'):
            next_path = next_path[:len(next_path) - len('()')]
            next_entity = getattr(next_entity, next_path)
            next_entity = next_entity()
        else:
            next_entity = getattr(next_entity, next_path)

    result_entity = next_entity

    return result_entity

# Задать либо полный путь path_to_entity, либо отдельные path_to_module (путь к модулю) и path_after_module (путь к сущности внутри модуля)
# search_by_module - Поиск по модулю, три значения: True/False или None если неизвестно, сравнивать точечно
class URLError(Exception):
    def __init__(self, search_by_module: Union[bool, None], path_to_entity: Optional[str], path_to_module: Optional[str], path_after_module: Optional[str]):
        self.search_by_module = search_by_module
        self.path_to_entity = path_to_entity
        self.path_to_module = path_to_module
        self.path_after_module = path_after_module

    def get_path(self):
        if self.path_to_entity:
            return self.path_to_entity
        elif self.path_to_module and self.path_after_module:
            return self.path_to_module + '/' + self.path_after_module

class FormatURLError(URLError):
    def __str__(self):
        return f"Недопустимый путь запроса {self.get_path()} Первая часть запроса - это путь к модулю, вторая - путь к сущности, переменной или функции"

class EntityNotFinded(URLError):
    def __str__(self):
        return f"Сущность {self.get_path()} не найдена"

defined_objects: dict[str, dict[str, dict]] = {}
objects: dict[str, Any] = {}
object_ids: dict[str, str] = {}

def write_object(entity, path: str, params: dict, search_by_module: bool):
    print('Запись в объект')
    id: str = ''
    path = path[1:] if path.startswith('/') else path
    if path in object_ids or path in objects:
        print('Берем существующий id')
        id = object_ids[path] if path in object_ids else path
    else:
        print('Генерация нового id')
        id = str(uuid.uuid4())  
        if not path.__contains__('()') and not params:
            object_ids[path] = id
    objects[id] = entity
    return id

# def json_parse(query: str) -> Union[dict, list, int, float, bool, None, str]:
#     # попытки
#     # 1 - в число
#     try:
#         return float(json.loads(query)) if query.__contains__('.') else int(json.loads(query))
#     except:
#         pass
#     # 2 - в строку
#     if query.startswith('"') and query.endswith('"'):
#         return str(json.loads(query))
#     # 3 - во все остальные типы данных, включая структуры списка и словаря
#     return json.loads(query)

class Handler(http.server.SimpleHTTPRequestHandler):
    def send_result(self, code: int, res: str):
        self.send_response(code)
        self.end_headers()
        self.wfile.write(res.encode(encoding='utf-8'))

    def get_entity(self, entity_path: str):
        # получение путей
        paths = [path for path in entity_path.split('/') if len(path) > 0]
        # print(paths, entity_path)
        print('начальная проверка несоответствия структуре пути запроса')
        print('Количество путей в запросе', len(paths))
        if len(paths) < 1 or len(paths) > 2:
            raise FormatURLError(None, entity_path, path_to_module=None, path_after_module=None)
        elif len(paths) == 1:
            print('если путь только один, то поиск происходит по id или закешированному пути')
            path = paths[0]
            search_by_module = False

            if path in object_ids:
                print('путь закеширован')
                return (objects[object_ids[path]], search_by_module)
            paths_to_entity = [path for path in path.split('.') if len(path) > 0]

            id: str = ''
            first_path = paths_to_entity[0][:len(paths_to_entity[0]) - len('()')] if paths_to_entity[0].endswith('()') else paths_to_entity[0]
            if first_path in objects:
                id = first_path

            if not id in objects:
                print("Если не закешировано, то ничего не найдено")
                raise EntityNotFinded(search_by_module, path, None, None)
            
            first_entity = objects[id]
            if paths_to_entity[0].endswith('()'):
                first_entity = first_entity()
            if len(paths_to_entity) == 1:
                return (first_entity, search_by_module)
            
            print("Поиск по закешированной сущности")
            entity = None
            try:
                entity = find_entity(first_entity, '.'.join(paths_to_entity[1:]))

                # if entity is None:
                #     raise EntityNotFinded(search_by_module, entity_path, None, None)
            except (ModuleNotFoundError, AttributeError) as ex:
                raise ex
            return (entity, search_by_module)

        else:
            print('стандартный поиск с сопоставлением базы имен')
            search_by_module = True
            if entity_path in object_ids:
                print('Путь закеширован')
                return (objects[object_ids[entity_path]], search_by_module)
            module_path, path = paths
            paths_to_entity = [path for path in path.split('.') if len(path) > 0]
            first_path = paths_to_entity[0][:len(paths_to_entity[0]) - len('()')] if paths_to_entity[0].endswith('()') else paths_to_entity[0]
            # all_path = path[:len(path) - len('()')] if path.endswith('()') else path
            print("Поиск с проверкой, что путь без скобок начинается с ключа в словаре")
            all_path = path.replace('()', '')
            print("Весь путь", all_path)
            is_module_path = module_path in defined_objects
            print("Путь к модулю есть?", is_module_path)
            if is_module_path:
                print("Пути к сущностям", defined_objects[module_path].keys())
                is_path_to_entity = find(lambda key_path: key_path.startswith(all_path), defined_objects[module_path].keys())
                print("Путь к сущности есть?", is_path_to_entity)
            if is_module_path and is_path_to_entity:
                entity = None
                try:
                    entity = find_entity(module_path, path)

                    # if entity is None:
                    #     raise EntityNotFinded(search_by_module, entity_path, None, None)
                except (ModuleNotFoundError, AttributeError) as ex:
                    raise ex
                return (entity, search_by_module)
            else:
                raise EntityNotFinded(search_by_module, None, module_path, path)

    def do_GET(self):
        try:
            if self.path == '/':
                self.send_result(200, 'Hello, Python API!')
                return
            
            parsed_url = urlparse(self.path)
            # путь первого запроса
            first_path = parsed_url.path
            query = parsed_url.query
            # параметры первого запроса
            params = parse_qs(query)

            def handling(next_path: str, next_params: dict):
                print('получение сущности')
                print('Запрос', next_path)
                print('Параметры', next_params)
                print("сначала пробуем распарсить как JSON")
                candidate_json = unquote(next_path[1:] if next_path.startswith('/') else next_path)
                # paths = candidate_json.split('/')
                try:
                    # путь от первого элемента, не учитываем слэш в начале
                    # unquote - для раскодирования символов запроса
                    # entity = json_parse(candidate_json)
                    entity = json.loads(candidate_json)
                    # для JSON-значения id нулевой
                    return (entity, 0)
                except (json.decoder.JSONDecodeError, TypeError) as ex:
                    print("Ошибка парсинга JSON, пробуем поиск сущности", ex)
                entity, search_by_module = self.get_entity(next_path)
                # try:
                #     entity, search_by_module = self.get_entity(next_path)
                # except EntityNotFinded as ex:
                #     if ex.search_by_module and next_path == first_path:
                #         raise ex
                #     print("Сущность не нашлась, зато можно перевести в строку JSON, т.к. не поиск по модулю или вложенный запрос")
                #     return (str(candidate_json), 0)
                print('Поиск происходил по модулю', search_by_module)
                # paths = [path for path in next_path.split('/') if len(path) > 0]
                # if not next_params and not paths[-1].endswith('()'):
                if not next_params:
                    print('без параметров вызова вернуть саму сущность')
                    id = write_object(entity, next_path, next_params, search_by_module)
                    # if next_path == first_path:
                    #     return (entity, id)
                    return (entity, id)
                else:
                    print('разбор параметров как подзапросов')
                    adapted_params = next_params.copy()
                    for param, next_url in next_params.items():
                        next_url = next_url[0]
                        print("Параметр", param)
                        print("Подзапрос", next_url)
                        parsed_next_url = urlparse(next_url)
                        next_entity, _ = handling(parsed_next_url.path, parse_qs(parsed_next_url.query))
                        adapted_params[param] = next_entity
                    try:
                        result_entity = entity(**adapted_params)
                    except TypeError as ex:
                        print("Ошибка при вызове функции с именованными аргументами", ex)
                        print("Строка исключения", ex.__str__())
                        print("Параметр __name__ сущности", entity.__name__)
                        is_unnamed_args = ex.__str__().__contains__("takes no keyword arguments") or ex.__str__().__contains__("got an unexpected keyword argument")
                        if is_unnamed_args:
                            values_of_adapted_params = adapted_params.values()
                            print(values_of_adapted_params)
                            result_entity = entity(*values_of_adapted_params)
                        else:
                            raise Exception("Ошибка при вызове функции")
                    id = write_object(result_entity, next_path, adapted_params, search_by_module)
                    return (result_entity, id)

                
            next_path = first_path
            next_params = params
            result, id = None, 0
            try:
                result, id = handling(next_path, next_params)
            # ошибка если количество путей отлично от 1 и 2
            except FormatURLError as ex:
                print(traceback.format_exc())
                self.send_result(400, f"Format URL error: {ex.__str__()}")
                return
            # ошибка поиска сущности
            except (EntityNotFinded, FileNotFoundError, ModuleNotFoundError, AttributeError) as ex:
                print(traceback.format_exc())
                self.send_result(404, f"Found error: {ex.__str__()}")
                return
            # ошибка если пытаются вызов от неисполняемой сущности, не конструктор, не функция и не метод
            except TypeError as ex:
                if ex.__str__().__contains__("object is not callable"):
                    print(traceback.format_exc())
                    self.send_result(400, f"Call error: {ex.__str__()}")
                    return
                raise ex
            # запрещенные к вызову функции
            except ValueError as ex:
                if ex.__str__().endswith("is forbidden"):
                    print(traceback.format_exc())
                    self.send_result(400, ex.__str__())
                    return
                raise ex

            response_result = {
                "result": result,
                "id": id
            }
            res = None
            try:
                res = json.dumps(response_result)
            except TypeError as ex:
                try:
                    s_result = str(result)
                except:
                    try:
                        s_result = result.__str__()
                    except:
                        try:
                            s_result = result.__name__
                        except Exception as ex:
                            raise ex
                res = json.dumps({"result": s_result, "id": id})
            
            print("Response result", res)
            self.send_result(200, res)

        except Exception as ex:
            print(traceback.format_exc())
            self.send_result(500, f"Server error: {ex.__str__()}")

def fill_defined_objects():
    global defined_objects
    # excluded_modules = list(filter(lambda excluded_entity: excluded_entity.endswith('.*'), conf.EXCLUDED_ENTITIES))
    excluded_modules = [excluded_entity[:len(excluded_entity) - len('.*')] for excluded_entity in conf.EXCLUDED_ENTITIES if excluded_entity.endswith('.*')]
    for module_path in conf.MODULES:
        print("Обработка входного пути", module_path)
        try:
            print("Получить абсолютный путь с помощью импорта")
            prepared_module_path = get_abs_path_to_module(module_path)
            module_paths = module_path.split('.')
            module_prefix = ".".join(module_paths[:-1]) if len(module_paths) > 1 else None
            print("module_prefix", module_prefix)
            print("абсолютный путь к модулю", prepared_module_path)
            if os.path.isfile(prepared_module_path):
                prepared_module_path = os.path.dirname(prepared_module_path)
        except ImportError:
            print("Получить абсолютный путь системными средствами")
            if not os.path.isabs(module_path):
                prepared_module_path = os.path.abspath(module_path)
            else:
                prepared_module_path = module_path
            if not os.path.exists(prepared_module_path):
                print(FileNotFoundError(f"Модуль {module_path} не найден"))
                continue
            module_prefix = None
        print("Prepared module path", prepared_module_path)
        defined_objects.update(get_objects(prepared_module_path, module_prefix, excluded_modules))
    for excluded_entity in conf.EXCLUDED_ENTITIES:
        if excluded_entity.endswith('.*'):
            print("Исключаемый модуль", excluded_entity)
            defined_objects = {module_path: entities for module_path, entities in defined_objects.items() if not excluded_entity.startswith(module_path)}
        else:
            print("Исключаемая сущность", excluded_entity)
            defined_objects = {module_path: {entity_path: entity_spec for entity_path, entity_spec in entities.items() if not (module_path + '.' + entity_path == excluded_entity)} for module_path, entities in defined_objects.items()}

def run_server():
    with socketserver.TCPServer(("localhost", conf.PORT), Handler) as httpd:
        print("Serving at port", conf.PORT)
        httpd.serve_forever()

def main():
    global defined_objects
    # if os.path.exists('last_conf.json'):
    #     with open('last_conf.json', 'r', encoding='utf-8') as fd:
    #         try:
    #             loaded = json.load(fd)
    #             is_attrs = loaded.keys() == [attr for attr in dir(conf) if not attr.startswith('__')]
    #             print("Ключи последней конфигурации аналогичны?", is_attrs)
    #             if is_attrs:
    #                 for attr in dir(conf):
    #                     if not attr.startswith('__'):
    #                         setattr(conf, attr, loaded[attr])
    #                 print("Последняя конфигурация была загружена")
    #         except:
    #             pass
    if os.path.exists('last_objects.json'):
        with open('last_objects.json', 'r', encoding='utf-8') as fd:
            defined_objects = json.load(fd)
    else:
        fill_defined_objects()
        with open('last_objects.json', 'w', encoding='utf-8') as fd:
            json.dump(defined_objects, fd)
    # conf_obj = {}
    # for attr in dir(conf):
    #     if not attr.startswith('__'):
    #         attrval = getattr(conf, attr)
    #         conf_obj[attr] = attrval
    # with open('last_conf.json', 'w', encoding='utf-8') as fd:
    #     json.dump(conf_obj, fd)
    # log(defined_objects)
    run_server()

    # pprint(defined_objects)
    # log(defined_objects)
    # with open('output.txt', 'w', encoding="utf-8") as fd:
    #     fd.write(json.dumps(defined_objects))

if "-t" in sys.argv and __name__ == "__main__":
    # Тестовый режим запуска

    for module_path in conf.MODULES:
        print(os.path.exists(module_path))

    path = get_abs_path_to_module("vk_api")
    with open(path, "r", encoding="utf-8") as fd:
        print(fd.read())
elif __name__ == "__main__":
    # Релизный режим запуска
    main()

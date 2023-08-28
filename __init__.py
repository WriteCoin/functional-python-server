import json
from pprint import pprint
from urllib.parse import parse_qs, unquote, urlparse
import uuid

from aiohttp import web

from WebAutomation.general_utils import *
import conf
from parse_obj import get_abs_path_to_module, get_objects


log_file = open("output.txt", "w", encoding="utf-8")


def log(msg):
    pprint(msg, stream=log_file)


def find_entity(module_path_or_entity, path):
    if isinstance(module_path_or_entity, str):
        module = importlib.import_module(module_path_or_entity)

        next_entity = module
    else:
        next_entity = module_path_or_entity

    # print(next_entity)

    for next_path in path.split("."):
        if next_path.endswith("()"):
            next_path = next_path[: len(next_path) - len("()")]
            next_entity = getattr(next_entity, next_path)
            next_entity = next_entity()
        else:
            next_entity = getattr(next_entity, next_path)

    result_entity = next_entity

    return result_entity


# Задать либо полный путь path_to_entity, либо отдельные path_to_module (путь к модулю) и path_after_module (путь к сущности внутри модуля)
# search_by_module - Поиск по модулю, три значения: True/False или None если неизвестно, сравнивать точечно
class URLError(Exception):
    def __init__(
        self,
        search_by_module: Union[bool, None],
        path_to_entity: Optional[str],
        path_to_module: Optional[str],
        path_after_module: Optional[str],
    ):
        self.search_by_module = search_by_module
        self.path_to_entity = path_to_entity
        self.path_to_module = path_to_module
        self.path_after_module = path_after_module

    def get_path(self):
        if self.path_to_entity:
            return self.path_to_entity
        elif self.path_to_module and self.path_after_module:
            return self.path_to_module + "/" + self.path_after_module


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
    print("Запись в объект")
    id: str = ""
    path = path[1:] if path.startswith("/") else path
    if path in object_ids or path in objects:
        print("Берем существующий id")
        id = object_ids[path] if path in object_ids else path
    else:
        print("Генерация нового id")
        id = str(uuid.uuid4())
        if not path.__contains__("()") and not params:
            object_ids[path] = id
    objects[id] = entity
    return id


def get_entity(entity_path: str):
    # получение путей
    paths = [path for path in entity_path.split("/") if len(path) > 0]
    # print(paths, entity_path)
    print("начальная проверка несоответствия структуре пути запроса")
    print("Количество путей в запросе", len(paths))
    if len(paths) < 1 or len(paths) > 2:
        raise FormatURLError(
            None, entity_path, path_to_module=None, path_after_module=None
        )
    elif len(paths) == 1:
        print(
            "если путь только один, то поиск происходит по id или закешированному пути"
        )
        path = paths[0]
        search_by_module = False

        if path in object_ids:
            print("путь закеширован")
            return (objects[object_ids[path]], search_by_module)
        paths_to_entity = [path for path in path.split(".") if len(path) > 0]

        id: str = ""
        first_path = (
            paths_to_entity[0][: len(paths_to_entity[0]) - len("()")]
            if paths_to_entity[0].endswith("()")
            else paths_to_entity[0]
        )
        if first_path in objects:
            id = first_path

        if not id in objects:
            print("Если не закешировано, то ничего не найдено")
            raise EntityNotFinded(search_by_module, path, None, None)

        first_entity = objects[id]
        if paths_to_entity[0].endswith("()"):
            first_entity = first_entity()
        if len(paths_to_entity) == 1:
            return (first_entity, search_by_module)

        print("Поиск по закешированной сущности")
        entity = None
        try:
            entity = find_entity(first_entity, ".".join(paths_to_entity[1:]))

            # if entity is None:
            #     raise EntityNotFinded(search_by_module, entity_path, None, None)
        except (ModuleNotFoundError, AttributeError) as ex:
            raise ex
        return (entity, search_by_module)

    else:
        print("стандартный поиск с сопоставлением базы имен")
        search_by_module = True
        if entity_path in object_ids:
            print("Путь закеширован")
            return (objects[object_ids[entity_path]], search_by_module)
        module_path, path = paths
        paths_to_entity = [path for path in path.split(".") if len(path) > 0]
        first_path = (
            paths_to_entity[0][: len(paths_to_entity[0]) - len("()")]
            if paths_to_entity[0].endswith("()")
            else paths_to_entity[0]
        )
        # all_path = path[:len(path) - len('()')] if path.endswith('()') else path
        print("Поиск с проверкой, что путь без скобок начинается с ключа в словаре")
        all_path = path.replace("()", "")
        print("Весь путь", all_path)
        is_module_path = module_path in defined_objects
        print("Путь к модулю есть?", is_module_path)
        if is_module_path:
            print("Пути к сущностям", defined_objects[module_path].keys())
            is_path_to_entity = find(
                lambda key_path: key_path.startswith(all_path),
                defined_objects[module_path].keys(),
            )
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


def handling(next_path: str, next_params: dict):
    print("получение сущности")
    print("Запрос", next_path)
    print("Параметры", next_params)
    print("сначала пробуем распарсить как JSON")
    candidate_json = unquote(next_path[1:] if next_path.startswith("/") else next_path)
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
    entity, search_by_module = get_entity(next_path)
    # try:
    #     entity, search_by_module = self.get_entity(next_path)
    # except EntityNotFinded as ex:
    #     if ex.search_by_module and next_path == first_path:
    #         raise ex
    #     print("Сущность не нашлась, зато можно перевести в строку JSON, т.к. не поиск по модулю или вложенный запрос")
    #     return (str(candidate_json), 0)
    print("Поиск происходил по модулю", search_by_module)
    # paths = [path for path in next_path.split('/') if len(path) > 0]
    # if not next_params and not paths[-1].endswith('()'):
    if not next_params:
        print("без параметров вызова вернуть саму сущность")
        id = write_object(entity, next_path, next_params, search_by_module)
        # if next_path == first_path:
        #     return (entity, id)
        return (entity, id)
    else:
        print("разбор параметров как подзапросов")
        adapted_params = next_params.copy()
        for param, next_url in next_params.items():
            next_url = next_url[0]
            print("Параметр", param)
            print("Подзапрос", next_url)
            parsed_next_url = urlparse(next_url)
            next_entity, _ = handling(
                parsed_next_url.path, parse_qs(parsed_next_url.query)
            )
            adapted_params[param] = next_entity
        try:
            result_entity = entity(**adapted_params)
        except TypeError as ex:
            print("Ошибка при вызове функции с именованными аргументами", ex)
            print("Строка исключения", ex.__str__())
            print("Параметр __name__ сущности", entity.__name__)
            is_unnamed_args = ex.__str__().__contains__(
                "takes no keyword arguments"
            ) or ex.__str__().__contains__("got an unexpected keyword argument")
            if is_unnamed_args:
                values_of_adapted_params = adapted_params.values()
                print(values_of_adapted_params)
                result_entity = entity(*values_of_adapted_params)
            else:
                raise Exception("Ошибка при вызове функции")
        id = write_object(result_entity, next_path, adapted_params, search_by_module)
        return (result_entity, id)


def send_result(code: int, res: str) -> web.Response:
    return web.Response(text=res, status=code)


async def handle_request(request) -> web.Response:
    try:
        path = request.match_info.get("path", "")

        print("path", path)

        # пустой запрос
        if path == "":
            return send_result(200, "Hello, Python API!")
        # игнорировать 'favicon.ico'
        if path == "favicon.ico":
            return send_result(200, path)

        params = parse_qs(path)

        next_path = path
        next_params = params
        result, id = None, 0
        try:
            result, id = handling(next_path, next_params)
        # ошибка если количество путей отлично от 1 и 2
        except FormatURLError as ex:
            print(traceback.format_exc())
            return send_result(400, f"Format URL error: {ex.__str__()}")
        # ошибка поиска сущности
        except (
            EntityNotFinded,
            FileNotFoundError,
            ModuleNotFoundError,
            AttributeError,
        ) as ex:
            print(traceback.format_exc())
            return send_result(404, f"Found error: {ex.__str__()}")
        # ошибка если пытаются вызов от неисполняемой сущности, не конструктор, не функция и не метод
        except TypeError as ex:
            if ex.__str__().__contains__("object is not callable"):
                print(traceback.format_exc())
                return send_result(400, f"Call error: {ex.__str__()}")
            raise ex
        # запрещенные к вызову функции
        except ValueError as ex:
            if ex.__str__().endswith("is forbidden"):
                print(traceback.format_exc())
                return send_result(400, ex.__str__())
            raise ex

        response_result = {"result": result, "id": id}
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
        return send_result(200, res)

    except Exception as ex:
        print(traceback.format_exc())
        return send_result(500, f"Server error: {ex.__str__()}")


def run_server():
    app = web.Application()
    app.add_routes([web.get('/', handle_request),
                    web.get('/{path:.+}', handle_request)])

    web.run_app(app, host="localhost", port=conf.PORT)


def fill_defined_objects():
    global defined_objects
    # excluded_modules = list(filter(lambda excluded_entity: excluded_entity.endswith('.*'), conf.EXCLUDED_ENTITIES))
    excluded_modules = [
        excluded_entity[: len(excluded_entity) - len(".*")]
        for excluded_entity in conf.EXCLUDED_ENTITIES
        if excluded_entity.endswith(".*")
    ]
    for module_path in conf.MODULES:
        print("Обработка входного пути", module_path)
        try:
            print("Получить абсолютный путь с помощью импорта")
            prepared_module_path = get_abs_path_to_module(module_path)
            module_paths = module_path.split(".")
            module_prefix = (
                ".".join(module_paths[:-1]) if len(module_paths) > 1 else None
            )
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
        defined_objects.update(
            get_objects(prepared_module_path, module_prefix, excluded_modules)
        )
    for excluded_entity in conf.EXCLUDED_ENTITIES:
        if excluded_entity.endswith(".*"):
            print("Исключаемый модуль", excluded_entity)
            defined_objects = {
                module_path: entities
                for module_path, entities in defined_objects.items()
                if not excluded_entity.startswith(module_path)
            }
        else:
            print("Исключаемая сущность", excluded_entity)
            defined_objects = {
                module_path: {
                    entity_path: entity_spec
                    for entity_path, entity_spec in entities.items()
                    if not (module_path + "." + entity_path == excluded_entity)
                }
                for module_path, entities in defined_objects.items()
            }


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
    if os.path.exists("last_objects.json"):
        with open("last_objects.json", "r", encoding="utf-8") as fd:
            defined_objects = json.load(fd)
    else:
        fill_defined_objects()
        with open("last_objects.json", "w", encoding="utf-8") as fd:
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

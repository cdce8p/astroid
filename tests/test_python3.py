# Licensed under the LGPL: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.en.html
# For details: https://github.com/pylint-dev/astroid/blob/main/LICENSE
# Copyright (c) https://github.com/pylint-dev/astroid/blob/main/CONTRIBUTORS.txt

import unittest
from textwrap import dedent

import pytest

from astroid import exceptions, nodes
from astroid.builder import AstroidBuilder, extract_node
from astroid.manager import AstroidManager


class Python3TC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = AstroidBuilder(AstroidManager())

    def test_starred_notation(self) -> None:
        astroid = self.builder.string_build("*a, b = [1, 2, 3]", "test", "test")

        # Get the star node
        node = next(next(next(astroid.get_children()).get_children()).get_children())

        self.assertTrue(isinstance(node.assign_type(), nodes.Assign))

    def test_yield_from(self) -> None:
        body = dedent(
            """
        def func():
            yield from iter([1, 2])
        """
        )
        astroid = self.builder.string_build(body)
        func = astroid.body[0]
        self.assertIsInstance(func, nodes.FunctionDef)
        yieldfrom_stmt = func.body[0]

        self.assertIsInstance(yieldfrom_stmt, nodes.Expr)
        self.assertIsInstance(yieldfrom_stmt.value, nodes.YieldFrom)
        self.assertEqual(yieldfrom_stmt.as_string(), "yield from iter([1, 2])")

    def test_yield_from_is_generator(self) -> None:
        body = dedent(
            """
        def func():
            yield from iter([1, 2])
        """
        )
        astroid = self.builder.string_build(body)
        func = astroid.body[0]
        self.assertIsInstance(func, nodes.FunctionDef)
        self.assertTrue(func.is_generator())

    def test_yield_from_as_string(self) -> None:
        body = dedent(
            """
        def func():
            yield from iter([1, 2])
            value = yield from other()
        """
        )
        astroid = self.builder.string_build(body)
        func = astroid.body[0]
        self.assertEqual(func.as_string().strip(), body.strip())

    # metaclass tests

    def test_simple_metaclass(self) -> None:
        astroid = self.builder.string_build("class Test(metaclass=type): pass")
        klass = astroid.body[0]

        metaclass = klass.metaclass()
        self.assertIsInstance(metaclass, nodes.ClassDef)
        self.assertEqual(metaclass.name, "type")

    def test_metaclass_error(self) -> None:
        astroid = self.builder.string_build("class Test(metaclass=typ): pass")
        klass = astroid.body[0]
        self.assertFalse(klass.metaclass())

    def test_metaclass_imported(self) -> None:
        astroid = self.builder.string_build(
            dedent(
                """
        from abc import ABCMeta
        class Test(metaclass=ABCMeta): pass"""
            )
        )
        klass = astroid.body[1]

        metaclass = klass.metaclass()
        self.assertIsInstance(metaclass, nodes.ClassDef)
        self.assertEqual(metaclass.name, "ABCMeta")

    def test_metaclass_multiple_keywords(self) -> None:
        astroid = self.builder.string_build(
            "class Test(magic=None, metaclass=type): pass"
        )
        klass = astroid.body[0]

        metaclass = klass.metaclass()
        self.assertIsInstance(metaclass, nodes.ClassDef)
        self.assertEqual(metaclass.name, "type")

    def test_as_string(self) -> None:
        body = dedent(
            """
        from abc import ABCMeta
        class Test(metaclass=ABCMeta): pass"""
        )
        astroid = self.builder.string_build(body)
        klass = astroid.body[1]

        self.assertEqual(
            klass.as_string(), "\n\nclass Test(metaclass=ABCMeta):\n    pass\n"
        )

    def test_old_syntax_works(self) -> None:
        astroid = self.builder.string_build(
            dedent(
                """
        class Test:
            __metaclass__ = type
        class SubTest(Test): pass
        """
            )
        )
        klass = astroid["SubTest"]
        metaclass = klass.metaclass()
        self.assertIsNone(metaclass)

    def test_metaclass_yes_leak(self) -> None:
        astroid = self.builder.string_build(
            dedent(
                """
        # notice `ab` instead of `abc`
        from ab import ABCMeta

        class Meta(metaclass=ABCMeta): pass
        """
            )
        )
        klass = astroid["Meta"]
        self.assertIsNone(klass.metaclass())

    def test_parent_metaclass(self) -> None:
        astroid = self.builder.string_build(
            dedent(
                """
        from abc import ABCMeta
        class Test(metaclass=ABCMeta): pass
        class SubTest(Test): pass
        """
            )
        )
        klass = astroid["SubTest"]
        metaclass = klass.metaclass()
        self.assertIsInstance(metaclass, nodes.ClassDef)
        self.assertEqual(metaclass.name, "ABCMeta")

    def test_metaclass_ancestors(self) -> None:
        astroid = self.builder.string_build(
            dedent(
                """
        from abc import ABCMeta

        class FirstMeta(metaclass=ABCMeta): pass
        class SecondMeta(metaclass=type):
            pass

        class Simple:
            pass

        class FirstImpl(FirstMeta): pass
        class SecondImpl(FirstImpl): pass
        class ThirdImpl(Simple, SecondMeta):
            pass
        """
            )
        )
        classes = {"ABCMeta": ("FirstImpl", "SecondImpl"), "type": ("ThirdImpl",)}
        for metaclass, names in classes.items():
            for name in names:
                impl = astroid[name]
                meta = impl.metaclass()
                self.assertIsInstance(meta, nodes.ClassDef)
                self.assertEqual(meta.name, metaclass)

    def test_annotation_support(self) -> None:
        astroid = self.builder.string_build(
            dedent(
                """
        def test(a: int, b: str, c: None, d, e,
                 *args: float, **kwargs: int)->int:
            pass
        """
            )
        )
        func = astroid["test"]
        self.assertIsInstance(func.args.varargannotation, nodes.Name)
        self.assertEqual(func.args.varargannotation.name, "float")
        self.assertIsInstance(func.args.kwargannotation, nodes.Name)
        self.assertEqual(func.args.kwargannotation.name, "int")
        self.assertIsInstance(func.returns, nodes.Name)
        self.assertEqual(func.returns.name, "int")
        arguments = func.args
        self.assertIsInstance(arguments.annotations[0], nodes.Name)
        self.assertEqual(arguments.annotations[0].name, "int")
        self.assertIsInstance(arguments.annotations[1], nodes.Name)
        self.assertEqual(arguments.annotations[1].name, "str")
        self.assertIsInstance(arguments.annotations[2], nodes.Const)
        self.assertIsNone(arguments.annotations[2].value)
        self.assertIsNone(arguments.annotations[3])
        self.assertIsNone(arguments.annotations[4])

        astroid = self.builder.string_build(
            dedent(
                """
        def test(a: int=1, b: str=2):
            pass
        """
            )
        )
        func = astroid["test"]
        self.assertIsInstance(func.args.annotations[0], nodes.Name)
        self.assertEqual(func.args.annotations[0].name, "int")
        self.assertIsInstance(func.args.annotations[1], nodes.Name)
        self.assertEqual(func.args.annotations[1].name, "str")
        self.assertIsNone(func.returns)

    def test_kwonlyargs_annotations_supper(self) -> None:
        node = self.builder.string_build(
            dedent(
                """
        def test(*, a: int, b: str, c: None, d, e):
            pass
        """
            )
        )
        func = node["test"]
        arguments = func.args
        self.assertIsInstance(arguments.kwonlyargs_annotations[0], nodes.Name)
        self.assertEqual(arguments.kwonlyargs_annotations[0].name, "int")
        self.assertIsInstance(arguments.kwonlyargs_annotations[1], nodes.Name)
        self.assertEqual(arguments.kwonlyargs_annotations[1].name, "str")
        self.assertIsInstance(arguments.kwonlyargs_annotations[2], nodes.Const)
        self.assertIsNone(arguments.kwonlyargs_annotations[2].value)
        self.assertIsNone(arguments.kwonlyargs_annotations[3])
        self.assertIsNone(arguments.kwonlyargs_annotations[4])

    def test_annotation_as_string(self) -> None:
        code1 = dedent(
            """
        def test(a, b: int = 4, c=2, f: 'lala' = 4) -> 2:
            pass"""
        )
        code2 = dedent(
            """
        def test(a: typing.Generic[T], c: typing.Any = 24) -> typing.Iterable:
            pass"""
        )
        for code in (code1, code2):
            func = extract_node(code)
            self.assertEqual(func.as_string(), code)

    def test_unpacking_in_dicts(self) -> None:
        code = "{'x': 1, **{'y': 2}}"
        node = extract_node(code)
        self.assertEqual(node.as_string(), code)
        assert isinstance(node, nodes.Dict)
        keys = [key for (key, _) in node.items]
        self.assertIsInstance(keys[0], nodes.Const)
        self.assertIsInstance(keys[1], nodes.DictUnpack)

    def test_nested_unpacking_in_dicts(self) -> None:
        code = "{'x': 1, **{'y': 2, **{'z': 3}}}"
        node = extract_node(code)
        self.assertEqual(node.as_string(), code)

    def test_unpacking_in_dict_getitem(self) -> None:
        node = extract_node("{1:2, **{2:3, 3:4}, **{5: 6}}")
        for key, expected in ((1, 2), (2, 3), (3, 4), (5, 6)):
            value = node.getitem(nodes.Const(key))
            self.assertIsInstance(value, nodes.Const)
            self.assertEqual(value.value, expected)

    @staticmethod
    def test_unpacking_in_dict_getitem_with_ref() -> None:
        node = extract_node(
            """
        a = {1: 2}
        {**a, 2: 3}  #@
        """
        )
        assert isinstance(node, nodes.Dict)

        for key, expected in ((1, 2), (2, 3)):
            value = node.getitem(nodes.Const(key))
            assert isinstance(value, nodes.Const)
            assert value.value == expected

    @staticmethod
    def test_unpacking_in_dict_getitem_uninferable() -> None:
        node = extract_node("{**a, 2: 3}")
        assert isinstance(node, nodes.Dict)

        with pytest.raises(exceptions.AstroidIndexError):
            node.getitem(nodes.Const(1))

        value = node.getitem(nodes.Const(2))
        assert isinstance(value, nodes.Const)
        assert value.value == 3

    def test_format_string(self) -> None:
        code = "f'{greetings} {person}'"
        node = extract_node(code)
        self.assertEqual(node.as_string(), code)

    def test_underscores_in_numeral_literal(self) -> None:
        pairs = [("10_1000", 101000), ("10_000_000", 10000000), ("0x_FF_FF", 65535)]
        for value, expected in pairs:
            node = extract_node(value)
            inferred = next(node.infer())
            self.assertIsInstance(inferred, nodes.Const)
            self.assertEqual(inferred.value, expected)

    def test_async_comprehensions(self) -> None:
        async_comprehensions = [
            extract_node(
                "async def f(): return __([i async for i in aiter() if i % 2])"
            ),
            extract_node(
                "async def f(): return __({i async for i in aiter() if i % 2})"
            ),
            extract_node(
                "async def f(): return __((i async for i in aiter() if i % 2))"
            ),
            extract_node(
                "async def f(): return __({i: i async for i in aiter() if i % 2})"
            ),
        ]
        non_async_comprehensions = [
            extract_node("async def f(): return __({i: i for i in iter() if i % 2})")
        ]

        for comp in async_comprehensions:
            self.assertTrue(comp.generators[0].is_async)
        for comp in non_async_comprehensions:
            self.assertFalse(comp.generators[0].is_async)

    def test_async_comprehensions_outside_coroutine(self):
        # When async and await will become keywords, async comprehensions
        # will be allowed outside of coroutines body
        comprehensions = [
            "[i async for i in aiter() if condition(i)]",
            "[await fun() async for fun in funcs]",
            "{await fun() async for fun in funcs}",
            "{fun: await fun() async for fun in funcs}",
            "[await fun() async for fun in funcs if await smth]",
            "{await fun() async for fun in funcs if await smth}",
            "{fun: await fun() async for fun in funcs if await smth}",
            "[await fun() async for fun in funcs]",
            "{await fun() async for fun in funcs}",
            "{fun: await fun() async for fun in funcs}",
            "[await fun() async for fun in funcs if await smth]",
            "{await fun() async for fun in funcs if await smth}",
            "{fun: await fun() async for fun in funcs if await smth}",
        ]

        for comp in comprehensions:
            node = extract_node(comp)
            self.assertTrue(node.generators[0].is_async)

    def test_async_comprehensions_as_string(self) -> None:
        func_bodies = [
            "return [i async for i in aiter() if condition(i)]",
            "return [await fun() for fun in funcs]",
            "return {await fun() for fun in funcs}",
            "return {fun: await fun() for fun in funcs}",
            "return [await fun() for fun in funcs if await smth]",
            "return {await fun() for fun in funcs if await smth}",
            "return {fun: await fun() for fun in funcs if await smth}",
            "return [await fun() async for fun in funcs]",
            "return {await fun() async for fun in funcs}",
            "return {fun: await fun() async for fun in funcs}",
            "return [await fun() async for fun in funcs if await smth]",
            "return {await fun() async for fun in funcs if await smth}",
            "return {fun: await fun() async for fun in funcs if await smth}",
        ]
        for func_body in func_bodies:
            code = dedent(
                f"""
            async def f():
                {func_body}"""
            )
            func = extract_node(code)
            self.assertEqual(func.as_string().strip(), code.strip())

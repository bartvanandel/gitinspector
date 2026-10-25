# coding: utf-8
#
# Copyright © 2012-2026 Ejwa Hosting AB. All rights reserved.
#
# This file is part of gitinspector.
#
# gitinspector is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# gitinspector is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with gitinspector. If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

try:
	import unittest2 as unittest
except ImportError:
	import unittest

from .harness import DEFAULT_AUTHOR, NAMES_ARE_UNRESTRICTED, Repository, analyze_blame, analyze_changes

class AttributionTest(unittest.TestCase):
	def setUp(self):
		self.repository = Repository()

	def tearDown(self):
		self.repository.remove()

	def test_lines_are_attributed_to_the_newest_name_of_their_email(self):
		self.repository.commit("first", {"a.py": "x = 1\n"}, "New Name", "x@example.com", "2015-03-01T12:00:00+0000")
		self.repository.commit("second", {"a.py": "x = 1\ny = 2\n"}, "Old Name", "x@example.com",
		                       "2015-01-01T12:00:00+0000")
		analyzed_changes = analyze_changes(self.repository)
		result = analyze_blame(self.repository, analyzed_changes)
		self.assertEqual(dict((key, entry.lines) for (key, entry) in result.blames.items()), {("New Name", "a.py"): 2})

	def test_files_without_extension_are_blamed_when_asked_for(self):
		self.repository.commit("add", {"Makefile": "all:\n\techo\n", "a.py": "x = 1\n"})
		analyzed_changes = analyze_changes(self.repository, file_types="*,py")
		result = analyze_blame(self.repository, analyzed_changes)
		self.assertEqual(sorted(filename for (author, filename) in result.blames), ["Makefile", "a.py"])
		self.assertEqual(result.blames[(DEFAULT_AUTHOR, "Makefile")].lines, 2)

class ComplexityAttributionTest(unittest.TestCase):
	def setUp(self):
		self.repository = Repository()

	def tearDown(self):
		self.repository.remove()

	def test_flat_and_nested_code_is_charged_to_its_author(self):
		self.repository.commit("flat", {"flat.py": "if x:\n    y = 1\n"}, "Flat Author", "flat@example.com",
		                       "2015-01-01T12:00:00+0000")
		self.repository.commit("nested", {"nested.js": "if (a) {\n    if (b) {\n        x();\n    }\n}\n"},
		                       "Nested Author", "nested@example.com", "2015-02-01T12:00:00+0000")

		analyzed_changes = analyze_changes(self.repository)
		result = analyze_blame(self.repository, analyzed_changes)

		flat = result.blames[("Flat Author", "flat.py")]
		nested = result.blames[("Nested Author", "nested.js")]
		self.assertEqual(flat.complexity, 1)
		self.assertEqual(flat.get_complexity(), 0.5)
		self.assertEqual(nested.complexity, 3)
		self.assertEqual(nested.get_complexity(), 0.6)

	def __commit_nested_code__(self):
		self.repository.commit("outer", {"nested.py": "if x:\n    if y:\n        a = 1\n"},
		                       "Outer Author", "outer@example.com", "2015-01-01T12:00:00+0000")
		self.repository.commit("inner", {"nested.py": "if x:\n    if y:\n        if z:\n            b = 2\n"},
		                       "Inner Author", "inner@example.com", "2015-06-01T12:00:00+0000")

	def test_structures_before_the_interval_still_nest_inner_lines(self):
		self.__commit_nested_code__()

		analyzed_changes = analyze_changes(self.repository, since="2015-03-01")
		result = analyze_blame(self.repository, analyzed_changes)

		self.assertEqual(sorted(result.blames), [("Inner Author", "nested.py")])
		self.assertEqual(result.blames[("Inner Author", "nested.py")].complexity, 3)
		self.assertEqual(result.blames[("Inner Author", "nested.py")].get_complexity(), 1.5)

	def test_structures_of_a_filtered_author_still_nest_inner_lines(self):
		self.__commit_nested_code__()

		analyzed_changes = analyze_changes(self.repository, exclude="author:Outer Author")
		result = analyze_blame(self.repository, analyzed_changes)

		self.assertEqual(sorted(result.blames), [("Inner Author", "nested.py")])
		self.assertEqual(result.blames[("Inner Author", "nested.py")].complexity, 3)

	def test_comments_add_neither_complexity_nor_executable_lines(self):
		self.repository.commit("commented", {"commented.py": "# if x:\nif x:\n    # for y in z:\n    y = 1\n"},
		                       "Comment Author", "comment@example.com")

		analyzed_changes = analyze_changes(self.repository)
		result = analyze_blame(self.repository, analyzed_changes)
		entry = result.blames[("Comment Author", "commented.py")]

		self.assertEqual(entry.complexity, 1)
		self.assertEqual(entry.comments, 2)
		self.assertEqual(entry.get_complexity(), 0.5)

class SpecialFilenameTest(unittest.TestCase):
	def setUp(self):
		self.repository = Repository()

	def tearDown(self):
		self.repository.remove()

	def test_files_with_quotes_in_their_names_are_blamed(self):
		files = {"`file_with_backticks`.txt": "one\ntwo\nthree\n",
		         "file 'with' single quotes.txt": "four\nfive\n",
		         "plain.txt": "six\n"}
		self.repository.commit("add files", files)

		analyzed_changes = analyze_changes(self.repository)
		result = analyze_blame(self.repository, analyzed_changes)

		blamed_files = sorted(filename for (author, filename) in result.blames)
		self.assertEqual(blamed_files, sorted(files))
		self.assertEqual(sum(entry.lines for entry in result.blames.values()), 6)

	@unittest.skipUnless(NAMES_ARE_UNRESTRICTED, "Windows does not allow a quote in a file name")
	def test_non_ascii_names_are_blamed(self):
		files = {"fil_ö.py": "print(1)\nprint(2)\n", "say \"hi\".py": "print(3)\n"}
		self.repository.commit("add files", files, "Jörg Müller", "jorg@example.com")

		analyzed_changes = analyze_changes(self.repository)
		result = analyze_blame(self.repository, analyzed_changes)

		self.assertEqual(sorted(result.blames), [("Jörg Müller", "fil_ö.py"), ("Jörg Müller", "say \"hi\".py")])
		self.assertEqual(sum(entry.lines for entry in result.blames.values()), 3)

from __future__ import unicode_literals

# This needs to stay as the first import, it sets up paths.
from gaetest_common import DummyPostData, fill_authors, NDBTestCase

from google.appengine.ext import ndb

from wtforms import Form, TextField, IntegerField, BooleanField, \
    SelectField, SelectMultipleField, FormField, FieldList

from wtforms_appengine.fields import \
    KeyPropertyField, \
    RepeatedKeyPropertyField,\
    PrefetchedKeyPropertyField,\
    JsonPropertyField

from wtforms_appengine.ndb import model_form

# import second_ndb_module

# Silence NDB logging
ndb.utils.DEBUG = False


GENRES = ['sci-fi', 'fantasy', 'other']


class Address(ndb.Model):
    line_1 = ndb.StringProperty()
    line_2 = ndb.StringProperty()
    city = ndb.StringProperty()
    country = ndb.StringProperty()


class Author(ndb.Model):
    name = ndb.StringProperty(required=True)
    city = ndb.StringProperty()
    age = ndb.IntegerProperty(required=True)
    is_admin = ndb.BooleanProperty(default=False)

    # Test both repeated choice-fields and non-repeated.
    genre = ndb.StringProperty(choices=GENRES)
    genres = ndb.StringProperty(choices=GENRES, repeated=True)

    address = ndb.StructuredProperty(Address)
    address_history = ndb.StructuredProperty(Address, repeated=True)


class Book(ndb.Model):
    author = ndb.KeyProperty(kind=Author)


class Collab(ndb.Model):
    authors = ndb.KeyProperty(kind=Author, repeated=True)


class TestKeyPropertyField(NDBTestCase):
    class F(Form):
        author = KeyPropertyField(reference_class=Author)

    def setUp(self):
        super(TestKeyPropertyField, self).setUp()
        self.authors = fill_authors(Author)
        self.first_author_key = self.authors[0].key

    def get_form(self, *args, **kwargs):
        form = self.F(*args, **kwargs)
        form.author.query = Author.query().order(Author.name)
        return form

    def test_no_data(self):
        form = self.get_form()

        assert not form.validate()
        ichoices = list(form.author.iter_choices())
        self.assertEqual(len(ichoices), len(self.authors))
        for author, (key, label, selected) in zip(self.authors, ichoices):
            self.assertEqual(key, author.key.urlsafe())

    def test_form_data(self):
        # Valid data
        form = self.get_form(
            DummyPostData(author=self.first_author_key.urlsafe()))

        assert form.validate(), "Form validation failed. %r" % form.errors

        ichoices = list(form.author.iter_choices())
        self.assertEqual(len(ichoices), len(self.authors))
        self.assertEqual(list(x[2] for x in ichoices), [True, False, False])

        # Bogus Data
        form = self.get_form(DummyPostData(author='fooflaf'))
        assert not form.validate()
        print list(form.author.iter_choices())
        assert all(x[2] is False for x in form.author.iter_choices())

    def test_obj_data(self):
        """
        When creating a form from an object, check that the form will render
        (hint: it didn't before)
        """
        author = Author.query().get()
        book = Book(author=author.key)
        book.put()

        form = self.F(DummyPostData(), book)

        str(form['author'])

    def test_populate_obj(self):
        author = Author.query().get()
        book = Book(author=author.key)
        book.put()

        form = self.F(DummyPostData(), book)

        book2 = Book()
        form.populate_obj(book2)
        self.assertEqual(book2.author, author.key)


class TestRepeatedKeyPropertyField(NDBTestCase):
    class F(Form):
        authors = RepeatedKeyPropertyField(reference_class=Author)

    def setUp(self):
        super(TestRepeatedKeyPropertyField, self).setUp()
        self.authors = fill_authors(Author)
        self.first_author_key = self.authors[0].key
        self.second_author_key = self.authors[1].key

    def get_form(self, *args, **kwargs):
        form = self.F(*args, **kwargs)
        form.authors.query = Author.query().order(Author.name)
        return form

    def test_no_data(self):
        form = self.get_form()
        zipped = zip(self.authors, form.authors.iter_choices())

        for author, (key, label, selected) in zipped:
            self.assertFalse(selected)
            self.assertEqual(key, author.key.urlsafe())

    def test_empty_form(self):
        form = self.get_form(DummyPostData(authors=[]))
        self.assertTrue(form.validate())

        inst = Collab()
        form.populate_obj(inst)
        self.assertEqual(inst.authors, [])

    def test_values(self):
        data = DummyPostData(authors=[
            self.first_author_key.urlsafe(),
            self.second_author_key.urlsafe()])

        form = self.get_form(data)

        assert form.validate(), "Form validation failed. %r" % form.errors

        inst = Collab()
        form.populate_obj(inst)
        self.assertEqual(
            inst.authors,
            [self.first_author_key,
             self.second_author_key])

    def test_bad_value(self):
        data = DummyPostData(authors=['foo'])
        form = self.get_form(data)
        self.assertFalse(form.validate())


class TestPrefetchedKeyPropertyField(TestKeyPropertyField):
    def get_form(self, *args, **kwargs):
        q = Author.query().order(Author.name)

        class F(Form):
            author = PrefetchedKeyPropertyField(query=q)

        return F(*args, **kwargs)


class TestJsonPropertyField(NDBTestCase):
    nosegae_datastore_v3 = True

    class F(Form):
        field = JsonPropertyField()

    def test_round_trip(self):
        # Valid data
        test_data = {u'a': {'b': 3, 'c': ['a', 1, False]}}

        form = self.F()
        form.process(data={'field': test_data})
        raw_string = form.field._value()
        assert form.validate()
        form2 = self.F()
        form2.process(formdata=DummyPostData(field=raw_string))
        assert form.validate()
        # Test that we get back the same structure we serialized
        self.assertEqual(test_data, form2.field.data)


class TestModelForm(NDBTestCase):
    EXPECTED_AUTHOR = [
        ('name', TextField),
        ('city', TextField),
        ('age', IntegerField),
        ('is_admin', BooleanField),
        ('genre', SelectField),
        ('genres', SelectMultipleField),
        ('address', FormField),
        ('address_history', FieldList),
    ]

    def test_author(self):
        form = model_form(Author)
        zipped = zip(self.EXPECTED_AUTHOR, form())

        for (expected_name, expected_type), field in zipped:
            self.assertEqual(field.name, expected_name)
            self.assertEqual(type(field), expected_type)

    def test_book(self):
        authors = set(x.key.urlsafe() for x in fill_authors(Author))
        authors.add('__None')
        form = model_form(Book)
        keys = set()
        for key, b, c in form().author.iter_choices():
            keys.add(key)

        self.assertEqual(authors, keys)

    def test_choices(self):
        form = model_form(Author)
        bound_form = form()

        # Sort both sets of choices. NDB stores the choices as a frozenset
        # and as such, ends up in the wtforms field unsorted.
        expected = sorted([(v, v) for v in GENRES])

        self.assertEqual(sorted(bound_form['genre'].choices), expected)
        self.assertEqual(sorted(bound_form['genres'].choices), expected)

    def test_choices_override(self):
        """
        Check that when we provide additional choices, they override
        what was specified, or set choices on the field.
        """
        choices = ['Cat', 'Pig', 'Cow', 'Spaghetti']
        expected = [(x, x) for x in choices]

        form = model_form(Author, field_args={
            'genres': {'choices': choices},
            'name': {'choices': choices}})

        bound_form = form()

        # For provided choices, they should be in the provided order
        self.assertEqual(bound_form['genres'].choices, expected)
        self.assertEqual(bound_form['name'].choices, expected)


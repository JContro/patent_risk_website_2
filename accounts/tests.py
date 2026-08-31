from django.test import TestCase
from django.contrib.auth import get_user_model
from accounts.models import Patent
from accounts.views import _build_query_filter


class BuildQueryFilterTest(TestCase):
    """Tests for the _build_query_filter helper function."""

    @classmethod
    def setUpTestData(cls):
        Patent.objects.create(
            publication_number='US10000001B2',
            title='Car Repair Kit',
            abstract='A kit for repairing automobiles.',
            publication_date='2020-01-01',
        )
        Patent.objects.create(
            publication_number='US10000002C1',
            title='Carpet Cleaning Device',
            abstract='A device for cleaning carpets effectively.',
            publication_date='2021-01-01',
        )
        Patent.objects.create(
            publication_number='US10000003A1',
            title='Neural Network System',
            abstract='A system using neural networks for pattern recognition.',
            publication_date='2022-01-01',
        )

    def test_word_boundary_does_not_match_substring(self):
        """'car' should match 'Car Repair Kit' but not 'Carpet Cleaning Device'."""
        q = _build_query_filter('car')
        results = list(Patent.objects.filter(q))
        pub_numbers = [p.publication_number for p in results]
        self.assertIn('US10000001B2', pub_numbers)
        self.assertNotIn('US10000002C1', pub_numbers)

    def test_word_boundary_in_abstract(self):
        """'automobiles' should match in abstract."""
        q = _build_query_filter('automobiles')
        results = list(Patent.objects.filter(q))
        pub_numbers = [p.publication_number for p in results]
        self.assertIn('US10000001B2', pub_numbers)
        self.assertNotIn('US10000002C1', pub_numbers)

    def test_multi_word_all_words_required(self):
        """Multi-word query requires all words as whole words in same field."""
        q = _build_query_filter('neural network')
        results = list(Patent.objects.filter(q))
        pub_numbers = [p.publication_number for p in results]
        self.assertIn('US10000003A1', pub_numbers)

    def test_multi_word_not_substring(self):
        """'car carpet' should not match anything (no field has both words)."""
        q = _build_query_filter('car carpet')
        results = list(Patent.objects.filter(q))
        self.assertEqual(len(results), 0)

    def test_publication_number_substring(self):
        """publication_number should still use substring matching."""
        q = _build_query_filter('US10000001')
        results = list(Patent.objects.filter(q))
        pub_numbers = [p.publication_number for p in results]
        self.assertIn('US10000001B2', pub_numbers)

    def test_empty_query_returns_no_filter(self):
        """Empty query should return Q() (no filtering)."""
        q = _build_query_filter('')
        results = list(Patent.objects.filter(q))
        self.assertEqual(len(results), 3)

    def test_whitespace_only_query_returns_no_filter(self):
        """Whitespace-only query should return Q() (no filtering)."""
        q = _build_query_filter('   ')
        results = list(Patent.objects.filter(q))
        self.assertEqual(len(results), 3)

    def test_case_insensitive(self):
        """Search should be case-insensitive."""
        q = _build_query_filter('CAR')
        results = list(Patent.objects.filter(q))
        pub_numbers = [p.publication_number for p in results]
        self.assertIn('US10000001B2', pub_numbers)
        self.assertNotIn('US10000002C1', pub_numbers)

    def test_regex_special_chars_escaped(self):
        """Query with regex special characters should be treated literally."""
        Patent.objects.create(
            publication_number='US10000004C1',
            title='C++ Programming Language Support',
            abstract='Methods for supporting C++ in compilers.',
            publication_date='2023-01-01',
        )
        q = _build_query_filter('C++')
        results = list(Patent.objects.filter(q))
        pub_numbers = [p.publication_number for p in results]
        self.assertIn('US10000004C1', pub_numbers)


class SearchPatentsWordBoundaryTest(TestCase):
    """Tests for the search_patents view with word-boundary matching."""

    @classmethod
    def setUpTestData(cls):
        Patent.objects.create(
            publication_number='US10000001B2',
            title='Car Repair Kit',
            abstract='A kit for repairing automobiles.',
            publication_date='2020-01-01',
        )
        Patent.objects.create(
            publication_number='US10000002C1',
            title='Carpet Cleaning Device',
            abstract='A device for cleaning carpets effectively.',
            publication_date='2021-01-01',
        )

    def test_search_view_no_substring_match(self):
        """Searching 'car' should not return 'Carpet Cleaning Device'."""
        response = self.client.get('/accounts/search/?q=car')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Car Repair Kit')
        self.assertNotContains(response, 'Carpet Cleaning Device')

    def test_search_view_case_insensitive(self):
        """Searching 'CAR' should match 'Car Repair Kit'."""
        response = self.client.get('/accounts/search/?q=CAR')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Car Repair Kit')
        self.assertNotContains(response, 'Carpet Cleaning Device')

    def test_search_view_multi_word(self):
        """Searching 'neural network' requires both words."""
        Patent.objects.create(
            publication_number='US10000003A1',
            title='Neural Network System',
            abstract='A system using neural networks for pattern recognition.',
            publication_date='2022-01-01',
        )
        response = self.client.get('/accounts/search/?q=neural+network')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Neural Network System')

    def test_search_view_publication_number(self):
        """Searching partial publication number should still match."""
        response = self.client.get('/accounts/search/?q=US10000001')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Car Repair Kit')

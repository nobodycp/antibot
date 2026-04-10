from unittest.mock import patch

from django.test import SimpleTestCase

from core.resilient_cache import (
    safe_cache_add,
    safe_cache_delete,
    safe_cache_get,
    safe_cache_incr,
    safe_cache_set,
)


class ResilientCacheTests(SimpleTestCase):
    @patch("core.resilient_cache.cache")
    def test_safe_get_returns_default_on_error(self, mock_cache):
        mock_cache.get.side_effect = RuntimeError("unavailable")
        self.assertIsNone(safe_cache_get("k"))
        self.assertEqual(safe_cache_get("k", default=[]), [])

    @patch("core.resilient_cache.cache")
    def test_safe_set_returns_false_on_error(self, mock_cache):
        mock_cache.set.side_effect = RuntimeError("unavailable")
        self.assertFalse(safe_cache_set("k", 1, 60))

    @patch("core.resilient_cache.cache")
    def test_safe_delete_returns_false_on_error(self, mock_cache):
        mock_cache.delete.side_effect = RuntimeError("unavailable")
        self.assertFalse(safe_cache_delete("k"))

    @patch("core.resilient_cache.cache")
    def test_safe_add_returns_false_on_error(self, mock_cache):
        mock_cache.add.side_effect = RuntimeError("unavailable")
        self.assertFalse(safe_cache_add("k", 1, 60))

    @patch("core.resilient_cache.cache")
    def test_safe_incr_propagates_value_error(self, mock_cache):
        mock_cache.incr.side_effect = ValueError("missing key")
        with self.assertRaises(ValueError):
            safe_cache_incr("k")

    @patch("core.resilient_cache.cache")
    def test_safe_incr_returns_none_on_backend_error(self, mock_cache):
        mock_cache.incr.side_effect = ConnectionError("down")
        self.assertIsNone(safe_cache_incr("k"))

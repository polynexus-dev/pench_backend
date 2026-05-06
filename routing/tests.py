from unittest.mock import patch, MagicMock
from django.test import TestCase


class TestTSPSolver(TestCase):
    """Unit tests for the OR-Tools TSP solver."""

    def test_solve_returns_valid_route(self):
        """Solver returns a route starting and ending at depot (index 0)."""
        from routing.services.tsp_solver import solve_tsp

        matrix = [
            [0, 10, 15, 20],
            [10, 0, 35, 25],
            [15, 35, 0, 30],
            [20, 25, 30, 0],
        ]
        with patch('routing.services.tsp_solver.TIME_LIMIT', 2):
            result = solve_tsp(matrix)

        self.assertIsNotNone(result)
        self.assertEqual(result[0], 0, 'Route must start at depot')
        self.assertEqual(result[-1], 0, 'Route must return to depot')
        self.assertEqual(len(result), 5, 'Must visit all 4 nodes + return')

    def test_solve_too_few_stops(self):
        from routing.services.tsp_solver import solve_tsp
        result = solve_tsp([[0]])
        self.assertIsNone(result)


class TestOSRMFallback(TestCase):
    """OSRM client falls back to Euclidean when the API is unavailable."""

    @patch('routing.services.osrm_client.requests.get')
    def test_fallback_on_network_error(self, mock_get):
        from routing.services.osrm_client import build_distance_matrix
        import requests as req_lib
        mock_get.side_effect = req_lib.RequestException('Connection refused')

        stops = [
            {'lat': 19.076, 'lon': 72.877},
            {'lat': 19.080, 'lon': 72.880},
            {'lat': 19.070, 'lon': 72.870},
        ]
        matrix = build_distance_matrix(stops)
        self.assertEqual(len(matrix), 3)
        self.assertEqual(len(matrix[0]), 3)
        self.assertEqual(matrix[0][0], 0.0)

    def test_raises_for_single_stop(self):
        from routing.services.osrm_client import build_distance_matrix
        with self.assertRaises(ValueError):
            build_distance_matrix([{'lat': 19.0, 'lon': 72.0}])


class TestAutoInvoice(TestCase):
    """Finance service: auto_invoice_on_delivery is idempotent."""

    def _make_order(self, total=500):
        from unittest.mock import MagicMock
        order = MagicMock()
        order.id = 'test-order-001'
        order.total = total
        return order

    @patch('finance.services.Invoice')
    def test_creates_invoice_first_call(self, MockInvoice):
        from finance.services import auto_invoice_on_delivery
        MockInvoice.objects.filter.return_value.first.return_value = None
        MockInvoice.objects.create.return_value = MagicMock(invoice_number='INV-2025-00001')

        order = self._make_order()
        invoice, created = auto_invoice_on_delivery(order)
        self.assertTrue(created)
        MockInvoice.objects.create.assert_called_once()

    @patch('finance.services.Invoice')
    def test_idempotent_second_call(self, MockInvoice):
        from finance.services import auto_invoice_on_delivery
        existing = MagicMock(invoice_number='INV-2025-00001')
        MockInvoice.objects.filter.return_value.first.return_value = existing

        order = self._make_order()
        invoice, created = auto_invoice_on_delivery(order)
        self.assertFalse(created)
        MockInvoice.objects.create.assert_not_called()


class TestDeductStock(TestCase):
    """Inventory service: deduct_stock_on_delivery raises on insufficient stock."""

    @patch('inventory.services.Stock')
    def test_raises_when_no_stock_record(self, MockStock):
        from inventory.services import deduct_stock_on_delivery, InsufficientStockError
        MockStock.objects.select_for_update.return_value.filter.return_value.exists.return_value = False

        item = MagicMock()
        item.product.name = 'Widget'
        item.quantity = 5
        order = MagicMock()
        order.items.select_related.return_value.all.return_value = [item]

        with self.assertRaises(InsufficientStockError):
            deduct_stock_on_delivery(order)

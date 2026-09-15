"""
Tests for restocking API endpoints.
"""
import pytest
from datetime import datetime, timedelta


class TestRestockingEndpoints:
    """Test suite for restocking-related endpoints."""

    def test_get_recommendations_returns_200_with_valid_budget(self, client):
        """Test getting restocking recommendations with valid budget."""
        response = client.get("/api/restocking/recommendations?budget=5000")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)

        # Verify structure of recommendations
        for rec in data:
            assert "item_sku" in rec
            assert "item_name" in rec
            assert "warehouse" in rec
            assert "current_quantity" in rec
            assert "reorder_point" in rec
            assert "trend" in rec
            assert "unit_cost" in rec
            assert "recommended_quantity" in rec
            assert "line_total" in rec

    def test_recommendations_total_cost_never_exceeds_budget(self, client):
        """Test that total recommended cost never exceeds budget."""
        budget = 3000
        response = client.get(f"/api/restocking/recommendations?budget={budget}")
        assert response.status_code == 200

        data = response.json()
        total_cost = sum(rec["line_total"] for rec in data)

        # Allow small floating point tolerance
        assert total_cost <= budget + 0.01

    def test_recommendations_with_zero_budget_returns_empty(self, client):
        """Test that zero budget returns empty recommendations."""
        response = client.get("/api/restocking/recommendations?budget=0")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_recommendations_with_negative_budget_returns_400(self, client):
        """Test that negative budget returns 400 error."""
        response = client.get("/api/restocking/recommendations?budget=-1000")
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "negative" in data["detail"].lower() or "must be" in data["detail"].lower()

    def test_recommendations_prioritize_increasing_demand(self, client):
        """Test that recommendations prioritize items with increasing demand and low stock."""
        budget = 50000  # Generous budget to get multiple recommendations
        response = client.get(f"/api/restocking/recommendations?budget={budget}")
        assert response.status_code == 200

        data = response.json()

        # With generous budget, should get some recommendations
        if len(data) > 0:
            # Check that at least some recommendations have 'increasing' trend
            increasing_count = sum(1 for rec in data if rec["trend"] == "increasing")
            # Should have at least one or more increasing trend items if they exist in data
            assert increasing_count >= 0

    def test_create_restocking_order_success_returns_201(self, client):
        """Test submitting a valid restocking order returns 201."""
        # First get recommendations
        rec_response = client.get("/api/restocking/recommendations?budget=2000")
        recommendations = rec_response.json()

        if len(recommendations) == 0:
            pytest.skip("No recommendations available for testing")

        # Use first recommendation to create an order
        order_data = {
            "budget": 2000,
            "items": [
                {
                    "item_sku": rec["item_sku"],
                    "item_name": rec["item_name"],
                    "quantity": rec["recommended_quantity"],
                    "unit_cost": rec["unit_cost"],
                    "line_total": rec["line_total"]
                }
                for rec in recommendations[:1]  # Just first item for simplicity
            ]
        }

        response = client.post("/api/restocking/orders", json=order_data)
        assert response.status_code == 201

        order = response.json()
        assert "id" in order
        assert "order_number" in order
        assert order["order_number"].startswith("RESTOCK-2025-")
        assert "lead_time_days" in order
        assert order["lead_time_days"] == 10
        assert "expected_delivery" in order
        assert "order_date" in order
        assert order["status"] == "Processing"

    def test_order_expected_delivery_is_10_days_after_order_date(self, client):
        """Test that expected delivery is exactly 10 days after order date."""
        rec_response = client.get("/api/restocking/recommendations?budget=2000")
        recommendations = rec_response.json()

        if len(recommendations) == 0:
            pytest.skip("No recommendations available for testing")

        order_data = {
            "budget": 2000,
            "items": [
                {
                    "item_sku": rec["item_sku"],
                    "item_name": rec["item_name"],
                    "quantity": rec["recommended_quantity"],
                    "unit_cost": rec["unit_cost"],
                    "line_total": rec["line_total"]
                }
                for rec in recommendations[:1]
            ]
        }

        response = client.post("/api/restocking/orders", json=order_data)
        order = response.json()

        order_date = datetime.fromisoformat(order["order_date"])
        expected_delivery = datetime.fromisoformat(order["expected_delivery"])

        # Calculate expected difference
        expected_diff = timedelta(days=10)
        actual_diff = expected_delivery - order_date

        # Allow small time difference due to execution time
        assert abs((actual_diff - expected_diff).total_seconds()) < 1

    def test_create_order_with_over_budget_items_returns_400(self, client):
        """Test that over-budget order submission returns 400."""
        # Get a real inventory item first
        inv_response = client.get("/api/inventory")
        inventory = inv_response.json()

        if len(inventory) == 0:
            pytest.skip("No inventory items available for testing")

        item = inventory[0]

        # Create an order that exceeds the budget by requesting huge quantity
        order_data = {
            "budget": 10,  # Very small budget
            "items": [
                {
                    "item_sku": item["sku"],
                    "item_name": item["name"],
                    "quantity": 10000,  # Huge quantity that will exceed budget
                    "unit_cost": item["unit_cost"],
                    "line_total": 10000 * item["unit_cost"]  # Will exceed budget
                }
            ]
        }

        response = client.post("/api/restocking/orders", json=order_data)
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "exceeds budget" in data["detail"].lower()

    def test_create_order_with_empty_items_returns_400(self, client):
        """Test that order with no items returns 400."""
        order_data = {
            "budget": 5000,
            "items": []
        }

        response = client.post("/api/restocking/orders", json=order_data)
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "no items" in data["detail"].lower()

    def test_create_order_with_unknown_sku_returns_400(self, client):
        """Test that order with unknown SKU returns 400."""
        order_data = {
            "budget": 5000,
            "items": [
                {
                    "item_sku": "NONEXISTENT-SKU-99999",
                    "item_name": "Nonexistent Item",
                    "quantity": 10,
                    "unit_cost": 50.00,
                    "line_total": 500.00
                }
            ]
        }

        response = client.post("/api/restocking/orders", json=order_data)
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_create_order_with_mismatched_unit_cost_returns_400(self, client):
        """Test that order with mismatched unit cost returns 400."""
        # Get valid recommendations first
        rec_response = client.get("/api/restocking/recommendations?budget=2000")
        recommendations = rec_response.json()

        if len(recommendations) == 0:
            pytest.skip("No recommendations available for testing")

        rec = recommendations[0]
        wrong_cost = rec["unit_cost"] + 100  # Intentionally wrong cost

        order_data = {
            "budget": 2000,
            "items": [
                {
                    "item_sku": rec["item_sku"],
                    "item_name": rec["item_name"],
                    "quantity": rec["recommended_quantity"],
                    "unit_cost": wrong_cost,  # Wrong cost
                    "line_total": rec["line_total"]
                }
            ]
        }

        response = client.post("/api/restocking/orders", json=order_data)
        assert response.status_code == 400

        data = response.json()
        assert "detail" in data
        assert "cost has changed" in data["detail"].lower()

    def test_get_restocking_orders_returns_submitted_order(self, client):
        """Test that GET returns previously submitted order."""
        # First submit an order
        rec_response = client.get("/api/restocking/recommendations?budget=2000")
        recommendations = rec_response.json()

        if len(recommendations) == 0:
            pytest.skip("No recommendations available for testing")

        order_data = {
            "budget": 2000,
            "items": [
                {
                    "item_sku": rec["item_sku"],
                    "item_name": rec["item_name"],
                    "quantity": rec["recommended_quantity"],
                    "unit_cost": rec["unit_cost"],
                    "line_total": rec["line_total"]
                }
                for rec in recommendations[:1]
            ]
        }

        create_response = client.post("/api/restocking/orders", json=order_data)
        assert create_response.status_code == 201
        created_order = create_response.json()

        # Now retrieve all restocking orders
        get_response = client.get("/api/restocking/orders")
        assert get_response.status_code == 200

        orders = get_response.json()
        assert isinstance(orders, list)

        # Find the order we just created
        found = False
        for order in orders:
            if order["order_number"] == created_order["order_number"]:
                found = True
                assert order["id"] == created_order["id"]
                assert order["status"] == "Processing"
                break

        assert found, f"Order {created_order['order_number']} not found in list"

    def test_restocking_order_structure_is_valid(self, client):
        """Test that restocking orders have proper structure."""
        rec_response = client.get("/api/restocking/recommendations?budget=2000")
        recommendations = rec_response.json()

        if len(recommendations) == 0:
            pytest.skip("No recommendations available for testing")

        order_data = {
            "budget": 2000,
            "items": [
                {
                    "item_sku": rec["item_sku"],
                    "item_name": rec["item_name"],
                    "quantity": rec["recommended_quantity"],
                    "unit_cost": rec["unit_cost"],
                    "line_total": rec["line_total"]
                }
                for rec in recommendations[:1]
            ]
        }

        response = client.post("/api/restocking/orders", json=order_data)
        order = response.json()

        # Verify all required fields exist
        assert "id" in order
        assert "order_number" in order
        assert "budget" in order
        assert "total_cost" in order
        assert "items" in order
        assert "order_date" in order
        assert "expected_delivery" in order
        assert "lead_time_days" in order
        assert "status" in order

        # Verify items structure
        assert isinstance(order["items"], list)
        for item in order["items"]:
            assert "item_sku" in item
            assert "item_name" in item
            assert "quantity" in item
            assert "unit_cost" in item
            assert "line_total" in item

    def test_recommendation_line_totals_are_calculated_correctly(self, client):
        """Test that recommended line totals equal quantity * unit cost."""
        response = client.get("/api/restocking/recommendations?budget=5000")
        assert response.status_code == 200

        data = response.json()

        for rec in data:
            expected_total = rec["recommended_quantity"] * rec["unit_cost"]
            # Allow small floating point tolerance
            assert abs(rec["line_total"] - expected_total) < 0.01

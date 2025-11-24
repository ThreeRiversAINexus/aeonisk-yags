"""
Tests for ItemTransfer schema validation.

Verifies multi-item transfer support and validation rules.
"""

import pytest
from pydantic import ValidationError
from scripts.aeonisk.multiagent.schemas.vendor_interaction import ItemTransfer


class TestItemTransferSchema:
    """Test ItemTransfer schema validation."""

    def test_valid_single_item_transfer(self):
        """Test valid transfer of single item."""
        transfer = ItemTransfer(
            from_character="Ash Kovalenko",
            to_character="Echo Rivera",
            items={"Medkit": 1},
            purpose="Sharing medical supplies"
        )
        assert transfer.from_character == "Ash Kovalenko"
        assert transfer.to_character == "Echo Rivera"
        assert transfer.items == {"Medkit": 1}
        assert transfer.purpose == "Sharing medical supplies"

    def test_valid_multi_item_transfer(self):
        """Test valid transfer of multiple items."""
        transfer = ItemTransfer(
            from_character="Ryn Thrace",
            to_character="Jace Kordell",
            items={"Medkit": 2, "Scanner": 1, "Ammo Pack": 3},
            purpose="Resupplying ally for mission"
        )
        assert transfer.items == {"Medkit": 2, "Scanner": 1, "Ammo Pack": 3}
        assert len(transfer.items) == 3

    def test_valid_transfer_without_purpose(self):
        """Test transfer without purpose field (optional)."""
        transfer = ItemTransfer(
            from_character="Ash",
            to_character="Echo",
            items={"Medkit": 1}
        )
        assert transfer.purpose is None

    def test_missing_from_character(self):
        """Test validation fails when from_character missing."""
        with pytest.raises(ValidationError) as exc_info:
            ItemTransfer(
                to_character="Echo",
                items={"Medkit": 1}
            )
        assert "from_character" in str(exc_info.value)

    def test_missing_to_character(self):
        """Test validation fails when to_character missing."""
        with pytest.raises(ValidationError) as exc_info:
            ItemTransfer(
                from_character="Ash",
                items={"Medkit": 1}
            )
        assert "to_character" in str(exc_info.value)

    def test_missing_items(self):
        """Test validation fails when items dict missing."""
        with pytest.raises(ValidationError) as exc_info:
            ItemTransfer(
                from_character="Ash",
                to_character="Echo"
            )
        assert "items" in str(exc_info.value)

    def test_empty_items_dict(self):
        """Test validation fails when items dict is empty."""
        with pytest.raises(ValidationError) as exc_info:
            ItemTransfer(
                from_character="Ash",
                to_character="Echo",
                items={}
            )
        assert "at least one item" in str(exc_info.value).lower()

    def test_all_zero_quantities(self):
        """Test validation fails when all item quantities are 0."""
        with pytest.raises(ValidationError) as exc_info:
            ItemTransfer(
                from_character="Ash",
                to_character="Echo",
                items={"Medkit": 0, "Scanner": 0}
            )
        assert "at least one item must have quantity > 0" in str(exc_info.value).lower()

    def test_mixed_zero_and_positive_quantities(self):
        """Test transfer with some zero quantities (only positive count)."""
        transfer = ItemTransfer(
            from_character="Ash",
            to_character="Echo",
            items={"Medkit": 2, "Scanner": 0}  # Scanner with 0 is weird but valid
        )
        assert transfer.items == {"Medkit": 2, "Scanner": 0}

    def test_character_name_min_length(self):
        """Test character name must have min 1 character."""
        with pytest.raises(ValidationError) as exc_info:
            ItemTransfer(
                from_character="",  # Empty string
                to_character="Echo",
                items={"Medkit": 1}
            )
        assert "from_character" in str(exc_info.value)

    def test_character_name_max_length(self):
        """Test character name must have max 100 characters."""
        long_name = "A" * 101
        with pytest.raises(ValidationError) as exc_info:
            ItemTransfer(
                from_character=long_name,
                to_character="Echo",
                items={"Medkit": 1}
            )
        assert "from_character" in str(exc_info.value)

    def test_purpose_max_length(self):
        """Test purpose must have max 200 characters."""
        long_purpose = "A" * 201
        with pytest.raises(ValidationError) as exc_info:
            ItemTransfer(
                from_character="Ash",
                to_character="Echo",
                items={"Medkit": 1},
                purpose=long_purpose
            )
        assert "purpose" in str(exc_info.value)

    def test_model_dump(self):
        """Test serialization to dict."""
        transfer = ItemTransfer(
            from_character="Ash",
            to_character="Echo",
            items={"Medkit": 2, "Scanner": 1},
            purpose="Sharing supplies"
        )
        data = transfer.model_dump()
        assert data["from_character"] == "Ash"
        assert data["to_character"] == "Echo"
        assert data["items"] == {"Medkit": 2, "Scanner": 1}
        assert data["purpose"] == "Sharing supplies"

    def test_realistic_item_transfer(self):
        """Test realistic item transfer scenario."""
        transfer = ItemTransfer(
            from_character="Ash Kovalenko",
            to_character="Echo Rivera",
            items={
                "Medical Kit": 2,
                "Portable Scanner": 1,
                "Energy Bar": 3
            },
            purpose="Resupplying wounded ally for extraction mission"
        )
        assert sum(transfer.items.values()) == 6  # Total items
        assert transfer.purpose is not None

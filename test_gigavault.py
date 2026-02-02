# test_gigavault.py
"""
Tests for GigaVault module.
"""

import unittest
from gigavault import GigaVault

class TestGigaVault(unittest.TestCase):
    """Test cases for GigaVault class."""
    
    def test_initialization(self):
        """Test class initialization."""
        instance = GigaVault()
        self.assertIsInstance(instance, GigaVault)
        
    def test_run_method(self):
        """Test the run method."""
        instance = GigaVault()
        self.assertTrue(instance.run())

if __name__ == "__main__":
    unittest.main()

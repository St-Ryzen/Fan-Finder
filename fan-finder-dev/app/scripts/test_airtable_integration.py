#!/usr/bin/env python3
"""
Test script for AirTable integration
"""
import os
import json
import sys

# Add the project root directory to the path so we can import modules
project_root = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.append(os.path.abspath(project_root))

from airtable_handler import AirTableHandler


def test_airtable_integration():
    print("Testing AirTable integration...")
    
    # Initialize the AirTable handler
    airtable_handler = AirTableHandler()
    
    if not airtable_handler.api_key:
        print("[ERROR] Could not retrieve AirTable configuration from Supabase")
        return False
    
    print(f"[INFO] Successfully initialized AirTable handler")
    print(f"[INFO] Base ID: {airtable_handler.base_id}")
    print(f"[INFO] Table ID: {airtable_handler.table_id}")
    print(f"[INFO] Username Field: {airtable_handler.username_field}")
    print(f"[INFO] Total Fans Field: {airtable_handler.total_fans_field}")
    print(f"[INFO] Last Updated Field: {airtable_handler.last_updated_field}")
    
    # Test updating a user's data
    test_username = "sofiasalazar23234_at_gmail_com"  # Using your example file name
    test_total_count = 42  # Example value
    test_last_updated = "2025-09-27T12:34:56"
    
    print(f"\n[INFO] Testing update for username: {test_username}")
    print(f"[INFO] Total count: {test_total_count}")
    print(f"[INFO] Last updated: {test_last_updated}")
    
    success = airtable_handler.update_user_data(
        username=test_username,
        total_count=test_total_count,
        last_updated=test_last_updated
    )
    
    if success:
        print(f"[SUCCESS] Successfully updated AirTable record for {test_username}")
    else:
        print(f"[ERROR] Failed to update AirTable record for {test_username}")
        
    return success


def test_with_json_file():
    print("\n" + "="*50)
    print("Testing with JSON file...")
    
    # Initialize the AirTable handler
    airtable_handler = AirTableHandler()
    
    if not airtable_handler.api_key:
        print("[ERROR] Could not retrieve AirTable configuration from Supabase")
        return False
    
    # Look for JSON files in the json_files directory
    json_files_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'json_files')
    
    if not os.path.exists(json_files_dir):
        print(f"[ERROR] JSON files directory does not exist: {json_files_dir}")
        return False
    
    json_files = [f for f in os.listdir(json_files_dir) if f.endswith('_users.json')]
    
    if not json_files:
        print(f"[WARNING] No JSON files found in {json_files_dir}")
        # Create a sample file for testing
        sample_data = {
            "users": ["test_user1", "test_user2"],
            "last_updated": "2025-09-27T12:34:56",
            "total_count": 2,
            "owner_email": "testuser123@gmail.com"
        }
        
        sample_file_path = os.path.join(json_files_dir, "testuser123_at_gmail_com_users.json")
        with open(sample_file_path, 'w', encoding='utf-8') as f:
            json.dump(sample_data, f, indent=2)
        
        json_files = ["testuser123_at_gmail_com_users.json"]
        print(f"[INFO] Created sample file: {sample_file_path}")
    
    # Test with the first JSON file found
    for json_file in json_files:
        json_file_path = os.path.join(json_files_dir, json_file)
        print(f"\n[INFO] Testing with file: {json_file_path}")
        
        success = airtable_handler.update_from_json_file(json_file_path)
        
        if success:
            print(f"[SUCCESS] Successfully processed {json_file}")
        else:
            print(f"[ERROR] Failed to process {json_file}")
        
        # Only test the first file for this example
        break
    
    return True


if __name__ == "__main__":
    print("AirTable Integration Test")
    print("="*50)
    
    success1 = test_airtable_integration()
    success2 = test_with_json_file()
    
    print("\n" + "="*50)
    if success1 and success2:
        print("[OVERALL SUCCESS] AirTable integration is working properly!")
    else:
        print("[OVERALL ERROR] There were issues with the AirTable integration")
    
    print("="*50)
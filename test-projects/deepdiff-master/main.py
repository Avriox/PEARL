from deepdiff import DeepDiff
import time

def generate_large_dict(size=1000):
    """Generate a large nested dictionary for testing"""
    data = {}
    for i in range(size):
        data[f"key_{i}"] = {
            "id": i,
            "name": f"item_{i}",
            "metadata": {
                "created": f"2024-01-{(i % 28) + 1:02d}",
                "tags": [f"tag_{j}" for j in range(i % 5)],
                "active": i % 2 == 0,
                "value": i * 3.14159
            },
            "nested": {
                "level1": {
                    "level2": {
                        "data": list(range(i % 10))
                    }
                }
            }
        }
    return data

def main():
    print("Testing DeepDiff with large data structures...")

    # Generate two large dictionaries
    dict1 = generate_large_dict(1000)

    dict2 = generate_large_dict(1000)

    # Modify some entries in dict2 to create differences
    dict2["key_100"]["name"] = "modified_item_100"
    dict2["key_200"]["metadata"]["active"] = not dict2["key_200"]["metadata"]["active"]
    dict2["key_300"]["metadata"]["tags"].append("new_tag")
    dict2["key_400"]["nested"]["level1"]["level2"]["data"].append(999)

    # Add some new keys to dict2
    dict2["new_key_1"] = {"type": "added", "value": 42}
    dict2["new_key_2"] = {"type": "added", "value": 84}




    diff = DeepDiff(dict1, dict2, verbose_level=2)



    list1 = list(range(0, 5000, 2))  # Even numbers
    list2 = list(range(0, 5000, 2))  # Same even numbers
    list2[100] = 9999  # Change one element
    list2.append(10000)  # Add new element
    list2.remove(500)   # Remove one element

    list_diff = DeepDiff(list1, list2)




if __name__ == "__main__":
    main()
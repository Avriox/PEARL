# Small

[BOTTLENECK]
Original: Regex patterns were compiled once using convert_item_or_items_into_compiled_regexes_else_none
Bottleneck: Not using compiled regex, compiling pattern on every search
Severity: Small
Type: Regex not compiled
[/BOTTLENECK]

```Python
def _skip_this(self, level: Any) -> bool:
    level_path = level.path()
    skip = False
    if self.exclude_paths and level_path in self.exclude_paths:
        skip = True
    if self.include_paths and level_path != 'root':
        if level_path not in self.include_paths:
            skip = True
            for prefix in self.include_paths:
                if prefix in level_path or level_path in prefix:
                    skip = False
                    break
    elif self.exclude_regex_paths and any(
            [re.search(exclude_regex_path.pattern if hasattr(exclude_regex_path, 'pattern') else exclude_regex_path,
                       level_path) for exclude_regex_path in self.exclude_regex_paths]):
        skip = True
    elif self.exclude_types_tuple and
        (isinstance(level.t1, self.exclude_types_tuple) or isinstance(level.t2, self.exclude_types_tuple)):
    skip = True
    elif self.exclude_obj_callback and
    (self.exclude_obj_callback(level.t1, level_path) or self.exclude_obj_callback(level.t2, level_path)):


skip = True
elif self.exclude_obj_callback_strict and
(self.exclude_obj_callback_strict(level.t1, level_path) and
 self.exclude_obj_callback_strict(level.t2, level_path)):
skip = True
elif self.include_obj_callback and level_path != 'root':
skip = True
if (self.include_obj_callback(level.t1, level_path) or self.include_obj_callback(level.t2, level_path)):
    skip = False
elif self.include_obj_callback_strict and level_path != 'root':
    skip = True
if (self.include_obj_callback_strict(level.t1, level_path) and
        self.include_obj_callback_strict(level.t2, level_path)):
    skip = False

return skip
```

[BOTTLENECK]
Original: Used generator expressions or efficient set operations
Bottleneck: Creating unnecessary intermediate lists for dict keys
Severity: Small
Type: Creating unnecessary intermediate lists
[/BOTTLENECK]

```Python

def _diff_dict(
        self,
        level: Any,
        parents_ids: FrozenSet[int] = frozenset([]),
        print_as_attribute: bool = False,
        override: bool = False,
        override_t1: Optional[Any] = None,
        override_t2: Optional[Any] = None,
        local_tree: Optional[Any] = None,
) -> None:
    if override:
        t1 = override_t1
        t2 = override_t2
    else:
        t1 = level.t1
        t2 = level.t2

    if print_as_attribute:
        item_added_key = "attribute_added"
        item_removed_key = "attribute_removed"
        rel_class = AttributeRelationship
    else:
        item_added_key = "dictionary_item_added"
        item_removed_key = "dictionary_item_removed"
        rel_class = DictRelationship

    if self.ignore_private_variables:
        t1_keys_list = list([key for key in list(t1.keys()) if
                             not (isinstance(key, str) and key.startswith('__')) and not self._skip_this_key(level,
                                                                                                             key)])
        t1_keys = SetOrdered(t1_keys_list)
        t2_keys_list = list([key for key in list(t2.keys()) if
                             not (isinstance(key, str) and key.startswith('__')) and not self._skip_this_key(level,
                                                                                                             key)])
        t2_keys = SetOrdered(t2_keys_list)
    else:
        t1_keys = SetOrdered(list([key for key in list(t1.keys()) if not self._skip_this_key(level, key)]))
        t2_keys = SetOrdered(list([key for key in list(t2.keys()) if not self._skip_this_key(level, key)]))

    if self.ignore_string_type_changes or self.ignore_numeric_type_changes or self.ignore_string_case:
        t1_clean_to_keys = self._get_clean_to_keys_mapping(keys=t1_keys, level=level)
        t2_clean_to_keys = self._get_clean_to_keys_mapping(keys=t2_keys, level=level)
        t1_keys = SetOrdered(t1_clean_to_keys.keys())
        t2_keys = SetOrdered(t2_clean_to_keys.keys())
    else:
        t1_clean_to_keys = t2_clean_to_keys = None

    t_keys_intersect = t2_keys & t1_keys
    t_keys_added = t2_keys - t_keys_intersect
    t_keys_removed = t1_keys - t_keys_intersect

    if self.threshold_to_diff_deeper:
        if self.exclude_paths:
            t_keys_union = {f"{level.path()}[{repr(key)}]" for key in (t2_keys | t1_keys)}
            t_keys_union -= self.exclude_paths
            t_keys_union_len = len(t_keys_union)
        else:
            t_keys_union_len = len(t2_keys | t1_keys)
        if t_keys_union_len > 1 and len(t_keys_intersect) / t_keys_union_len < self.threshold_to_diff_deeper:
            self._report_result('values_changed', level, local_tree=local_tree)
            return

    for key in t_keys_added:
        if self._count_diff() is StopIteration:
            return

        key = t2_clean_to_keys[key] if t2_clean_to_keys else key
        change_level = level.branch_deeper(
            notpresent,
            t2[key],
            child_relationship_class=rel_class,
            child_relationship_param=key,
            child_relationship_param2=key,
        )
        self._report_result(item_added_key, change_level, local_tree=local_tree)

    for key in t_keys_removed:
        if self._count_diff() is StopIteration:
            return

        key = t1_clean_to_keys[key] if t1_clean_to_keys else key
        change_level = level.branch_deeper(
            t1[key],
            notpresent,
            child_relationship_class=rel_class,
            child_relationship_param=key,
            child_relationship_param2=key,
        )
        self._report_result(item_removed_key, change_level, local_tree=local_tree)

    for key in t_keys_intersect:
        if self._count_diff() is StopIteration:
            return

        key1 = t1_clean_to_keys[key] if t1_clean_to_keys else key
        key2 = t2_clean_to_keys[key] if t2_clean_to_keys else key
        item_id = id(t1[key1])
        if parents_ids and item_id in parents_ids:
            continue
        parents_ids_added = add_to_frozen_set(parents_ids, item_id)

        next_level = level.branch_deeper(
            t1[key1],
            t2[key2],
            child_relationship_class=rel_class,
            child_relationship_param=key,
            child_relationship_param2=key,
        )
        self._diff(next_level, parents_ids_added, local_tree=local_tree)
```
# Translation Reference Guide

This document provides a comprehensive reference for translating the MeshCore Hub web dashboard.

## File Structure

Translation files are JSON files named by language code (e.g., `en.json`, `es.json`, `fr.json`) and located in `/src/meshcore_hub/web/static/locales/`.

## Variable Interpolation

Many translations use `{{variable}}` syntax for dynamic content. These must be preserved exactly:

```json
"total": "{{count}} total"
```

When translating, keep the variable names unchanged:
```json
"total": "{{count}} au total"  // French example
```

## Translation Sections

### 1. `entities`

Core entity names used throughout the application. These are referenced by other translations for composition.

| Key | English | Context |
|-----|---------|---------|
| `home` | Home | Homepage/breadcrumb navigation |
| `dashboard` | Dashboard | Main dashboard page |
| `nodes` | Nodes | Mesh network nodes (plural) |
| `node` | Node | Single mesh network node |
| `node_detail` | Node Detail | Node details page |
| `advertisements` | Advertisements | Network advertisements (plural) |
| `advertisement` | Advertisement | Single advertisement |
| `messages` | Messages | Network messages (plural) |
| `message` | Message | Single message |
| `map` | Map | Network map page |
| `members` | Members | Network members (plural) |
| `member` | Member | Single network member |
| `admin` | Admin | Admin panel |
| `tags` | Tags | Node metadata tags (plural) |
| `tag` | Tag | Single tag |

**Usage:** These are used with composite patterns. For example, `t('common.add_entity', { entity: t('entities.node') })` produces "Add Node".

### 2. `common`

Reusable patterns and UI elements used across multiple pages.

#### Actions

| Key | English | Context |
|-----|---------|---------|
| `filter` | Filter | Filter button/action |
| `clear` | Clear | Clear action |
| `clear_filters` | Clear Filters | Reset all filters |
| `search` | Search | Search button/action |
| `cancel` | Cancel | Cancel button in dialogs |
| `delete` | Delete | Delete button |
| `edit` | Edit | Edit button |
| `move` | Move | Move button |
| `save` | Save | Save button |
| `save_changes` | Save Changes | Save changes button |
| `add` | Add | Add button |
| `close` | close | Close button (lowercase for accessibility) |
| `sign_in` | Sign In | Authentication sign in |
| `sign_out` | Sign Out | Authentication sign out |
| `go_home` | Go Home | Return to homepage button |

#### Composite Patterns with Entity

These patterns use `{{entity}}` variable - the entity name is provided dynamically:

| Key | English | Example Output |
|-----|---------|----------------|
| `add_entity` | Add {{entity}} | "Add Node", "Add Tag" |
| `add_new_entity` | Add New {{entity}} | "Add New Member" |
| `edit_entity` | Edit {{entity}} | "Edit Tag" |
| `delete_entity` | Delete {{entity}} | "Delete Member" |
| `delete_all_entity` | Delete All {{entity}} | "Delete All Tags" |
| `move_entity` | Move {{entity}} | "Move Tag" |
| `move_entity_to_another_node` | Move {{entity}} to Another Node | "Move Tag to Another Node" |
| `copy_entity` | Copy {{entity}} | "Copy Tags" |
| `copy_all_entity_to_another_node` | Copy All {{entity}} to Another Node | "Copy All Tags to Another Node" |
| `view_entity` | View {{entity}} | "View Node" |
| `recent_entity` | Recent {{entity}} | "Recent Advertisements" |
| `total_entity` | Total {{entity}} | "Total Nodes" |
| `all_entity` | All {{entity}} | "All Messages" |

#### Empty State Patterns

These patterns indicate when data is absent. Use `{{entity}}` in lowercase (e.g., "nodes", not "Nodes"):

| Key | English | Context |
|-----|---------|---------|
| `no_entity_found` | No {{entity}} found | Search/filter returned no results |
| `no_entity_recorded` | No {{entity}} recorded | No historical records exist |
| `no_entity_defined` | No {{entity}} defined | No configuration/definitions exist |
| `no_entity_in_database` | No {{entity}} in database | Database is empty |
| `no_entity_configured` | No {{entity}} configured | System not configured |
| `no_entity_yet` | No {{entity}} yet | Empty state, expecting data later |
| `entity_not_found_details` | {{entity}} not found: {{details}} | Specific item not found with details |
| `page_not_found` | Page not found | 404 error message |

#### Confirmation Patterns

Used in delete/move dialogs. Variables: `{{entity}}`, `{{name}}`, `{{count}}`:

| Key | English | Context |
|-----|---------|---------|
| `delete_entity_confirm` | Are you sure you want to delete {{entity}} <strong>{{name}}</strong>? | Single item delete confirmation |
| `delete_all_entity_confirm` | Are you sure you want to delete all {{count}} {{entity}} from <strong>{{name}}</strong>? | Bulk delete confirmation |
| `cannot_be_undone` | This action cannot be undone. | Warning in delete dialogs |

#### Success Messages

Toast/flash messages after successful operations:

| Key | English | Context |
|-----|---------|---------|
| `entity_added_success` | {{entity}} added successfully | After creating new item |
| `entity_updated_success` | {{entity}} updated successfully | After updating item |
| `entity_deleted_success` | {{entity}} deleted successfully | After deleting item |
| `entity_moved_success` | {{entity}} moved successfully | After moving tag to another node |
| `all_entity_deleted_success` | All {{entity}} deleted successfully | After bulk delete |
| `copy_all_entity_description` | Copy all {{count}} {{entity}} from <strong>{{name}}</strong> to another node. | Copy operation description |

#### Navigation & Status

| Key | English | Context |
|-----|---------|---------|
| `previous` | Previous | Pagination previous |
| `next` | Next | Pagination next |
| `loading` | Loading... | Loading indicator |
| `error` | Error | Error state |
| `failed_to_load_page` | Failed to load page | Page load error |

#### Counts & Metrics

| Key | English | Context |
|-----|---------|---------|
| `total` | {{count}} total | Total count display |
| `shown` | {{count}} shown | Filtered count display |
| `count_entity` | {{count}} {{entity}} | Generic count with entity |

#### Form Fields & Labels

| Key | English | Context |
|-----|---------|---------|
| `type` | Type | Type field/column header |
| `name` | Name | Name field/column header |
| `key` | Key | Key field (for tags) |
| `value` | Value | Value field (for tags) |
| `time` | Time | Time column header |
| `actions` | Actions | Actions column header |
| `updated` | Updated | Last updated timestamp |
| `view_details` | View Details | View details link |
| `all_types` | All Types | "All types" filter option |
| `node_type` | Node Type | Node type field |
| `show` | Show | Show/display action |
| `search_placeholder` | Search by name, ID, or public key... | Search input placeholder |
| `contact` | Contact | Contact information field |
| `description` | Description | Description field |
| `callsign` | Callsign | Amateur radio callsign field |
| `tags` | Tags | Tags label/header |
| `last_seen` | Last Seen | Last seen timestamp (table header) |
| `first_seen_label` | First seen: | First seen label (inline with colon) |
| `last_seen_label` | Last seen: | Last seen label (inline with colon) |
| `location` | Location | Geographic location |
| `public_key` | Public Key | Node public key |
| `received` | Received | Received timestamp |
| `received_by` | Received By | Received by field |
| `receivers` | Receivers | Multiple receivers |
| `from` | From | Message sender |
| `unnamed` | Unnamed | Fallback for unnamed items |
| `unnamed_node` | Unnamed Node | Fallback for unnamed nodes |

**Note:** Keys ending in `_label` have colons and are used inline. Keys without `_label` are for table headers.

### 3. `links`

Platform and external link labels:

| Key | English | Context |
|-----|---------|---------|
| `website` | Website | Website link label |
| `github` | GitHub | GitHub link label (preserve capitalization) |
| `discord` | Discord | Discord link label |
| `youtube` | YouTube | YouTube link label (preserve capitalization) |
| `profile` | Profile | Radio profile label |

### 4. `time`

Time-related labels and formats:

| Key | English | Context |
|-----|---------|---------|
| `days_ago` | {{count}}d ago | Days ago (abbreviated) |
| `hours_ago` | {{count}}h ago | Hours ago (abbreviated) |
| `minutes_ago` | {{count}}m ago | Minutes ago (abbreviated) |
| `less_than_minute` | <1m ago | Less than one minute ago |
| `last_7_days` | Last 7 days | Last 7 days label |
| `per_day_last_7_days` | Per day (last 7 days) | Per day over last 7 days |
| `over_time_last_7_days` | Over time (last 7 days) | Over time last 7 days |
| `activity_per_day_last_7_days` | Activity per day (last 7 days) | Activity chart label |

### 5. `node_types`

Mesh network node type labels:

| Key | English | Context |
|-----|---------|---------|
| `chat` | Chat | Chat node type |
| `repeater` | Repeater | Repeater/relay node type |
| `room` | Room | Room/group node type |
| `unknown` | Unknown | Unknown node type fallback |

### 6. `home`

Homepage-specific content:

| Key | English | Context |
|-----|---------|---------|
| `welcome_default` | Welcome to the {{network_name}} mesh network dashboard. Monitor network activity, view connected nodes, and explore message history. | Default welcome message |
| `all_discovered_nodes` | All discovered nodes | Stat description |
| `network_info` | Network Info | Network info card title |
| `network_activity` | Network Activity | Activity chart title |
| `meshcore_attribution` | Our local off-grid mesh network is made possible by | Attribution text before MeshCore logo |
| `frequency` | Frequency | Radio frequency label |
| `bandwidth` | Bandwidth | Radio bandwidth label |
| `spreading_factor` | Spreading Factor | LoRa spreading factor label |
| `coding_rate` | Coding Rate | LoRa coding rate label |
| `tx_power` | TX Power | Transmit power label |
| `advertisements` | Advertisements | Homepage stat label |
| `messages` | Messages | Homepage stat label |

**Note:** MeshCore tagline "Connecting people and things, without using the internet" is hardcoded in English and should not be translated (trademark).

### 7. `dashboard`

Dashboard page content:

| Key | English | Context |
|-----|---------|---------|
| `all_discovered_nodes` | All discovered nodes | Stat label |
| `recent_channel_messages` | Recent Channel Messages | Recent messages card title |
| `channel` | Channel {{number}} | Channel label with number |

### 8. `nodes`

Node-specific labels:

| Key | English | Context |
|-----|---------|---------|
| `scan_to_add` | Scan to add as contact | QR code instruction |

### 9. `advertisements`

Currently empty - advertisements page uses common patterns.

### 10. `messages`

Message type labels:

| Key | English | Context |
|-----|---------|---------|
| `type_direct` | Direct | Direct message type |
| `type_channel` | Channel | Channel message type |
| `type_contact` | Contact | Contact message type |
| `type_public` | Public | Public message type |

### 11. `map`

Map page content:

| Key | English | Context |
|-----|---------|---------|
| `show_labels` | Show Labels | Toggle to show node labels |
| `infrastructure_only` | Infrastructure Only | Toggle to show only infrastructure nodes |
| `legend` | Legend: | Map legend header |
| `infrastructure` | Infrastructure | Infrastructure node category |
| `public` | Public | Public node category |
| `nodes_on_map` | {{count}} nodes on map | Status text with coordinates |
| `nodes_none_have_coordinates` | {{count}} nodes (none have coordinates) | Status text without coordinates |
| `gps_description` | Nodes are placed on the map based on GPS coordinates from node reports or manual tags. | Map data source explanation |
| `owner` | Owner: | Node owner label |
| `role` | Role: | Member role label |
| `select_destination_node` | -- Select destination node -- | Dropdown placeholder |

### 12. `members`

Members page content:

| Key | English | Context |
|-----|---------|---------|
| `empty_state_description` | To display network members, create a members.yaml file in your seed directory. | Empty state instructions |
| `members_file_format` | Members File Format | Documentation section title |
| `members_file_description` | Create a YAML file at <code>$SEED_HOME/members.yaml</code> with the following structure: | File creation instructions |
| `members_import_instructions` | Run <code>meshcore-hub collector seed</code> to import members.<br/>To associate nodes with members, add a <code>member_id</code> tag to nodes in <code>node_tags.yaml</code>. | Import instructions (HTML allowed) |

### 13. `not_found`

404 page content:

| Key | English | Context |
|-----|---------|---------|
| `description` | The page you're looking for doesn't exist or has been moved. | 404 description |

### 14. `custom_page`

Custom markdown page errors:

| Key | English | Context |
|-----|---------|---------|
| `failed_to_load` | Failed to load page | Page load error |

### 15. `admin`

Admin panel content:

| Key | English | Context |
|-----|---------|---------|
| `access_denied` | Access Denied | Access denied heading |
| `admin_not_enabled` | The admin interface is not enabled. | Admin disabled message |
| `admin_enable_hint` | Set <code>WEB_ADMIN_ENABLED=true</code> to enable admin features. | Configuration hint (HTML allowed) |
| `auth_required` | Authentication Required | Auth required heading |
| `auth_required_description` | You must sign in to access the admin interface. | Auth required description |
| `welcome` | Welcome to the admin panel. | Admin welcome message |
| `members_description` | Manage network members and operators. | Members card description |
| `tags_description` | Manage custom tags and metadata for network nodes. | Tags card description |

### 16. `admin_members`

Admin members page:

| Key | English | Context |
|-----|---------|---------|
| `network_members` | Network Members ({{count}}) | Page heading with count |
| `member_id` | Member ID | Member ID field label |
| `member_id_hint` | Unique identifier (letters, numbers, underscore) | Member ID input hint |
| `empty_state_hint` | Click "Add Member" to create the first member. | Empty state hint |

**Note:** Confirmation and success messages use `common.*` patterns.

### 17. `admin_node_tags`

Admin node tags page:

| Key | English | Context |
|-----|---------|---------|
| `select_node` | Select Node | Section heading |
| `select_node_placeholder` | -- Select a node -- | Dropdown placeholder |
| `load_tags` | Load Tags | Load button |
| `move_warning` | This will move the tag from the current node to the destination node. | Move operation warning |
| `copy_all` | Copy All | Copy all button |
| `copy_all_info` | Tags that already exist on the destination node will be skipped. Original tags remain on this node. | Copy operation info |
| `delete_all` | Delete All | Delete all button |
| `delete_all_warning` | All tags will be permanently deleted. | Delete all warning |
| `destination_node` | Destination Node | Destination node field |
| `tag_key` | Tag Key | Tag key field |
| `for_this_node` | for this node | Suffix for "No tags found for this node" |
| `empty_state_hint` | Add a new tag below. | Empty state hint |
| `select_a_node` | Select a Node | Empty state heading |
| `select_a_node_description` | Choose a node from the dropdown above to view and manage its tags. | Empty state description |
| `copied_entities` | Copied {{copied}} tag(s), skipped {{skipped}} | Copy operation result message |

**Note:** Titles, confirmations, and success messages use `common.*` patterns.

### 18. `footer`

Footer content:

| Key | English | Context |
|-----|---------|---------|
| `powered_by` | Powered by | "Powered by" attribution |

## Translation Tips

1. **Preserve HTML tags:** Some strings contain `<code>`, `<strong>`, or `<br/>` tags - keep these intact.

2. **Preserve variables:** Keep `{{variable}}` placeholders exactly as-is, only translate surrounding text.

3. **Entity composition:** Many translations reference `entities.*` keys. When translating entities, consider how they'll work in composite patterns (e.g., "Add {{entity}}" should make sense with "Node", "Tag", etc.).

4. **Capitalization:**
   - Entity names should follow your language's capitalization rules for UI elements
   - Inline labels (with colons) typically use sentence case
   - Table headers typically use title case
   - Action buttons can vary by language convention

5. **Colons:** Keys ending in `_label` include colons in English. Adjust punctuation to match your language's conventions for inline labels.

6. **Plurals:** Some languages have complex plural rules. You may need to add plural variants for `{{count}}` patterns. Consult the i18n library documentation for plural support.

7. **Length:** UI space is limited. Try to keep translations concise, especially for button labels and table headers.

8. **Brand names:** Preserve "MeshCore", "GitHub", "YouTube" capitalization.

## Testing Your Translation

1. Create your translation file: `locales/xx.json` (where `xx` is your language code)
2. Copy the structure from `en.json`
3. Translate all values, preserving all variables and HTML
4. Test in the application by setting the language
5. Check all pages for:
   - Text overflow/truncation
   - Proper variable interpolation
   - Natural phrasing in context

## Getting Help

If you're unsure about the context of a translation key, check:
1. The "Context" column in this reference
2. The JavaScript files in `/src/meshcore_hub/web/static/js/spa/pages/`
3. Grep for the key: `grep -r "t('section.key')" src/`

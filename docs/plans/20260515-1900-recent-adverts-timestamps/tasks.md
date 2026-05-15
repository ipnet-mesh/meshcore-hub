# Tasks: Fix Recent Advertisements Date Always Showing Today

## Implementation

- [ ] Add `public_key: Optional[str] = Query(None)` parameter to `list_advertisements` in `src/meshcore_hub/api/routes/advertisements.py`
- [ ] Add filter clause `if public_key: query = query.where(Advertisement.public_key == public_key)`
- [ ] Add test for `public_key` query parameter filtering in `tests/test_api/test_advertisements.py`
- [ ] Verify test covers: ads match requested key, ads with other keys excluded

## Validation

- [ ] `pytest tests/test_api/test_advertisements.py -v` passes
- [ ] `pre-commit run --all-files` passes

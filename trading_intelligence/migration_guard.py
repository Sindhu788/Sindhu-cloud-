"""Pure production-import decision gate. This module never connects or writes.

An approved empty import must run in one transaction with an advisory lock and
a repeated empty-schema assertion. Store a migration-id/payload-hash receipt in
that same transaction. A retry with a matching receipt AND verified row hashes,
relationships and sequences is a no-op. Every partial/different target refuses
the import; there is deliberately no repair, upsert, delete or overwrite path.
"""


def import_decision(*, explicitly_approved, destination_empty, backup_valid,
                    test_migration_valid, secrets_scan_valid,
                    expected_payload_hash, receipt_payload_hash=None,
                    destination_integrity_matches=False):
    if not isinstance(expected_payload_hash,str) or len(expected_payload_hash)!=64 or any(c not in '0123456789abcdef' for c in expected_payload_hash):
        raise ValueError('Expected SHA-256 payload fingerprint is required')
    if receipt_payload_hash is not None:
        if receipt_payload_hash==expected_payload_hash and destination_integrity_matches:
            return {'action':'NOOP_ALREADY_IMPORTED','write_allowed':False}
        return {'action':'REFUSE_EXISTING_OR_PARTIAL_DATA','write_allowed':False}
    if not destination_empty:
        return {'action':'REFUSE_EXISTING_OR_PARTIAL_DATA','write_allowed':False}
    if not all((backup_valid,test_migration_valid,secrets_scan_valid)):
        return {'action':'REFUSE_FAILED_VALIDATION','write_allowed':False}
    if not explicitly_approved:
        return {'action':'AWAITING_EXPLICIT_APPROVAL','write_allowed':False}
    return {'action':'IMPORT_EMPTY_IN_SINGLE_TRANSACTION','write_allowed':True,
            'required_recheck':'Acquire advisory lock, then repeat empty-schema assertion before CREATE/INSERT'}

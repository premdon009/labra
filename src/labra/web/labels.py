"""The words staff see for stored codes."""

SEX_LABELS = {"M": "Male", "F": "Female", "O": "Other"}
KIND_LABELS = {
    "doctor": "Doctor",
    "clinic": "Clinic",
    "hospital": "Hospital",
    "corporate": "Company",
    "self": "Self",
}
MODE_LABELS = {"cash": "Cash", "upi": "UPI", "card": "Card"}
COLLECTION_LABELS = {"walk_in": "Walk-in", "home": "Home collection"}
BILL_STATUS_LABELS = {"open": "Due", "paid": "Paid", "cancelled": "Cancelled"}
SAMPLE_STATUS_LABELS = {
    "pending": "To collect",
    "collected": "Collected",
    "received": "In the lab",
    "rejected": "Rejected",
    "redraw": "Collect again",
    "cancelled": "Cancelled",
}
TEST_STATUS_LABELS = {
    "ordered": "To collect",
    "collected": "On its way",
    "in_lab": "In the lab",
    "resulted": "Waiting for verification",
    "sent_out": "With an outside lab",
    "verified": "Verified",
    "released": "Released",
    "cancelled": "Cancelled",
}
TEST_EVENT_LABELS = {
    "registered": "Registered",
    "collected": "Sample collected",
    "routed": "Routed",
    "received": "Received in the lab",
    "sent": "Sent to the outside lab",
    "received_back": "Result received",
    "resulted": "Submitted for verification",
    "verified": "Verified",
    "reopened": "Reopened",
}
CRITICAL_MODE_LABELS = {
    "phone": "By phone",
    "in_person": "In person",
    "message": "By message",
    "email": "By email",
}

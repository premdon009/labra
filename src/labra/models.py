"""Every table, in one import. Alembic's env and the app import this module."""

from labra.adapters.identity_local import LocalCredential
from labra.auth.models import LoginAttempt, UserSession
from labra.billing.models import Bill, BillLine, Payment, Refund
from labra.catalog.models import (
    CommentPreset,
    Department,
    Package,
    PackageItem,
    Price,
    ReferenceBand,
    ReferenceRange,
    SpecimenType,
    Test,
    TestMethod,
    TestParameter,
)
from labra.core.db import Base
from labra.core.models import (
    AuditLog,
    Consent,
    ConsentNotice,
    EventOutbox,
    NumberSeries,
    Setting,
    StoredFile,
)
from labra.extlabs.models import ExternalLab, ExternalLabRate
from labra.ops.models import OpsRun
from labra.org.models import AppUser, Branch, Role, RolePermission, UserBranchRole
from labra.patients.models import Patient, Referrer
from labra.printing.models import LetterheadLayout
from labra.reports.models import Report, ReportDelivery, ReportPrint, ReportTest
from labra.results.models import (
    CriticalNotification,
    ExternalDocument,
    ExternalDocumentTest,
    OrderTestEvent,
    Result,
    ResultRevision,
    Verification,
)
from labra.visits.models import OrderItem, OrderTest, Sample, Visit

__all__ = [
    "AppUser",
    "AuditLog",
    "Base",
    "Bill",
    "BillLine",
    "Branch",
    "CommentPreset",
    "Consent",
    "ConsentNotice",
    "CriticalNotification",
    "Department",
    "EventOutbox",
    "ExternalDocument",
    "ExternalDocumentTest",
    "ExternalLab",
    "ExternalLabRate",
    "LetterheadLayout",
    "LocalCredential",
    "LoginAttempt",
    "NumberSeries",
    "OpsRun",
    "OrderItem",
    "OrderTest",
    "OrderTestEvent",
    "Package",
    "PackageItem",
    "Patient",
    "Payment",
    "Price",
    "ReferenceBand",
    "ReferenceRange",
    "Referrer",
    "Refund",
    "Report",
    "ReportDelivery",
    "ReportPrint",
    "ReportTest",
    "Result",
    "ResultRevision",
    "Role",
    "RolePermission",
    "Sample",
    "Setting",
    "SpecimenType",
    "StoredFile",
    "Test",
    "TestMethod",
    "TestParameter",
    "UserBranchRole",
    "UserSession",
    "Verification",
    "Visit",
]

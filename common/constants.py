"""Shared constants for the traffic generator project."""

# XML tag and attribute names
XML_TAG_PACKET = "packet"
XML_TAG_HEADER = "header"
XML_TAG_FIELD = "field"

XML_ATTR_NAME = "name"
XML_ATTR_TOTAL_BIT_LENGTH = "totalBitLength"
XML_ATTR_BIT_LENGTH = "bitLength"
XML_ATTR_TYPE = "type"
XML_ATTR_DEFAULT_VALUE = "defaultValue"

# XML encoding
XML_ENCODING = "UTF-8"
XML_VERSION = "1.0"

# Minimum valid bit length for a field (1 byte)
MIN_FIELD_BIT_LENGTH = 8

# Byte alignment requirement
BIT_ALIGNMENT = 8

# BOOLEAN fields are always exactly this many bits
BOOLEAN_BIT_LENGTH = 8

# Allowed attributes per element (structural validation)
ALLOWED_PACKET_ATTRS = {XML_ATTR_NAME, XML_ATTR_TOTAL_BIT_LENGTH}
ALLOWED_HEADER_ATTRS = {XML_ATTR_NAME}
ALLOWED_FIELD_ATTRS = {XML_ATTR_NAME, XML_ATTR_TYPE, XML_ATTR_BIT_LENGTH, XML_ATTR_DEFAULT_VALUE}

# Deprecated / forbidden attributes that must not appear
FORBIDDEN_ATTRS = {"startByte", "bytePosition", "totalSize", "offset", "startBit"}

# Allowed child tags
ALLOWED_PACKET_CHILDREN = {XML_TAG_HEADER}
ALLOWED_HEADER_CHILDREN = {XML_TAG_HEADER, XML_TAG_FIELD}

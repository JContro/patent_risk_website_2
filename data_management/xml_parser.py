"""
XML parsing utilities for extracting patent data from USPTO XML format.
Handles us-patent-application and us-patent-grant elements.
"""

import xml.etree.ElementTree as ET


def extract_text(element):
    """Extract all text content from an element and its children."""
    if element is None:
        return None
    text = element.text or ""
    for child in element:
        text += extract_text(child) or ""
        text += child.tail or ""
    return text.strip()


def extract_document_id(doc_id_elem):
    """Extract document ID information."""
    if doc_id_elem is None:
        return None

    return {
        "country": extract_text(doc_id_elem.find("country")),
        "doc_number": extract_text(doc_id_elem.find("doc-number")),
        "kind": extract_text(doc_id_elem.find("kind")),
        "date": extract_text(doc_id_elem.find("date"))
    }


def extract_classification(class_elem):
    """Extract classification information."""
    if class_elem is None:
        return None

    return {
        "section": extract_text(class_elem.find("section")),
        "class": extract_text(class_elem.find("class")),
        "subclass": extract_text(class_elem.find("subclass")),
        "main_group": extract_text(class_elem.find("main-group")),
        "subgroup": extract_text(class_elem.find("subgroup")),
        "symbol_position": extract_text(class_elem.find("symbol-position")),
        "classification_value": extract_text(class_elem.find("classification-value")),
        "text": extract_text(class_elem.find("text"))
    }


def extract_person(person_elem):
    """Extract person information from addressbook."""
    if person_elem is None:
        return None

    addressbook = person_elem.find("addressbook")
    if addressbook is None:
        return None

    address_elem = addressbook.find("address")
    address = None
    if address_elem is not None:
        address = {
            "city": extract_text(address_elem.find("city")),
            "state": extract_text(address_elem.find("state")),
            "country": extract_text(address_elem.find("country"))
        }

    return {
        "first_name": extract_text(addressbook.find("first-name")),
        "last_name": extract_text(addressbook.find("last-name")),
        "organization": extract_text(addressbook.find("orgname")),
        "role": extract_text(addressbook.find("role")),
        "address": address,
        "sequence": person_elem.get("sequence")
    }


def extract_claim(claim_elem):
    """Extract claim information."""
    if claim_elem is None:
        return None

    def extract_claim_text(claim_text_elem):
        """Recursively extract claim text."""
        if claim_text_elem is None:
            return None

        text = extract_text(claim_text_elem)

        # Get nested claim-text elements
        nested = []
        for child in claim_text_elem.findall("claim-text"):
            nested_text = extract_claim_text(child)
            if nested_text:
                nested.append(nested_text)

        return {
            "text": text,
            "nested": nested if nested else None
        }

    claim_text = claim_elem.find("claim-text")

    return {
        "id": claim_elem.get("id"),
        "num": claim_elem.get("num"),
        "claim_text": extract_claim_text(claim_text) if claim_text is not None else None
    }


def extract_patent(patent_elem):
    """Extract all data from a single us-patent-application or us-patent-grant element."""

    patent_data = {
        "attributes": {
            "lang": patent_elem.get("lang"),
            "dtd_version": patent_elem.get("dtd-version"),
            "file": patent_elem.get("file"),
            "status": patent_elem.get("status"),
            "id": patent_elem.get("id"),
            "country": patent_elem.get("country"),
            "date_produced": patent_elem.get("date-produced"),
            "date_publ": patent_elem.get("date-publ")
        }
    }

    # Extract bibliographic data
    # Handle both application and grant bibliographic data
    biblio = (patent_elem.find("us-bibliographic-data-application") or
              patent_elem.find("us-bibliographic-data-grant"))
    if biblio is not None:
        # Publication reference
        pub_ref = biblio.find("publication-reference")
        if pub_ref is not None:
            patent_data["publication"] = extract_document_id(
                pub_ref.find("document-id"))

        # Application reference
        app_ref = biblio.find("application-reference")
        if app_ref is not None:
            patent_data["application"] = {
                "appl_type": app_ref.get("appl-type"),
                "document_id": extract_document_id(app_ref.find("document-id"))
            }

        # Application series code
        series_code = biblio.find("us-application-series-code")
        if series_code is not None:
            patent_data["application_series_code"] = extract_text(series_code)

        # Priority claims
        priority_claims = biblio.find("priority-claims")
        if priority_claims is not None:
            patent_data["priority_claims"] = []
            for claim in priority_claims.findall("priority-claim"):
                patent_data["priority_claims"].append({
                    "sequence": claim.get("sequence"),
                    "kind": claim.get("kind"),
                    "document_id": extract_document_id(claim.find("document-id"))
                })

        # IPC Classifications
        ipcr = biblio.find("classifications-ipcr")
        if ipcr is not None:
            patent_data["classifications_ipcr"] = []
            for classification in ipcr.findall("classification-ipcr"):
                class_data = extract_classification(classification)
                if class_data:
                    patent_data["classifications_ipcr"].append(class_data)

        # CPC Classifications
        cpc = biblio.find("classifications-cpc")
        if cpc is not None:
            patent_data["classifications_cpc"] = {
                "main": extract_classification(cpc.find("main-cpc/classification-cpc")),
                "further": []
            }
            further_cpc = cpc.find("further-cpc")
            if further_cpc is not None:
                for classification in further_cpc.findall("classification-cpc"):
                    class_data = extract_classification(classification)
                    if class_data:
                        patent_data["classifications_cpc"]["further"].append(
                            class_data)

        # Invention title
        title = biblio.find("invention-title")
        if title is not None:
            patent_data["title"] = extract_text(title)

        # Inventors
        us_parties = biblio.find("us-parties")
        if us_parties is not None:
            inventors_elem = us_parties.find("inventors")
            if inventors_elem is not None:
                patent_data["inventors"] = []
                for inventor in inventors_elem.findall("inventor"):
                    person = extract_person(inventor)
                    if person:
                        patent_data["inventors"].append(person)

            # Applicants
            applicants_elem = us_parties.find("us-applicants")
            if applicants_elem is not None:
                patent_data["applicants"] = []
                for applicant in applicants_elem.findall("us-applicant"):
                    person = extract_person(applicant)
                    if person:
                        patent_data["applicants"].append(person)

        # Assignees
        assignees_elem = biblio.find("assignees")
        if assignees_elem is not None:
            patent_data["assignees"] = []
            for assignee in assignees_elem.findall("assignee"):
                person = extract_person(assignee)
                if person:
                    patent_data["assignees"].append(person)

    # Abstract
    abstract = patent_elem.find("abstract")
    if abstract is not None:
        patent_data["abstract"] = extract_text(abstract)

    # Claims
    claims = patent_elem.find("claims")
    if claims is not None:
        patent_data["claims"] = []
        for claim in claims.findall("claim"):
            claim_data = extract_claim(claim)
            if claim_data:
                patent_data["claims"].append(claim_data)

    # Description (extract headings and first few paragraphs only to keep size manageable)
    description = patent_elem.find("description")
    if description is not None:
        patent_data["description"] = {
            "headings": [],
            "paragraphs_sample": []
        }

        for heading in description.findall("heading"):
            patent_data["description"]["headings"].append({
                "level": heading.get("level"),
                "text": extract_text(heading)
            })

        # Get first 5 paragraphs as sample
        for i, para in enumerate(description.findall("p")[:5]):
            patent_data["description"]["paragraphs_sample"].append({
                "id": para.get("id"),
                "num": para.get("num"),
                "text": extract_text(para)
            })

    # Drawings info (just metadata, not the actual images)
    drawings = patent_elem.find("drawings")
    if drawings is not None:
        patent_data["drawings"] = {
            "count": len(drawings.findall("figure")),
            "figures": []
        }
        for figure in drawings.findall("figure"):
            patent_data["drawings"]["figures"].append({
                "id": figure.get("id"),
                "num": figure.get("num")
            })

    return patent_data


def contains_keywords(patent_data, keywords):
    """
    Check if patent contains any of the keywords (case-insensitive) in title, abstract, or claims.
    Returns True if any keyword is found in text fields.
    """
    if not keywords:
        return True

    text_fields = []

    # Title
    if "title" in patent_data and patent_data["title"]:
        text_fields.append(patent_data["title"])

    # Abstract
    if "abstract" in patent_data and patent_data["abstract"]:
        text_fields.append(patent_data["abstract"])

    # Claims text
    if "claims" in patent_data and patent_data["claims"]:
        for claim in patent_data["claims"]:
            if claim and "claim_text" in claim and claim["claim_text"]:
                claim_text_obj = claim["claim_text"]
                if isinstance(claim_text_obj, dict) and "text" in claim_text_obj:
                    text_fields.append(claim_text_obj["text"])

    # Combine all text
    combined_text = " ".join(text_fields).lower()

    # Check each keyword
    for keyword in keywords:
        if keyword.lower() in combined_text:
            return True

    return False

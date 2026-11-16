from __future__ import annotations

"""Read-only CW-derived FILE/Function semantic comparison projection.

The canonical document is the only EXPECTED source. Its authored identities
are not inferred from source path. Imported Code IR must bind separately via
an exact marker or approved provenance before any comparison.
"""

import copy
from collections import Counter
from typing import Any


def build_canonical_structuretree(document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(document, dict) or not isinstance(document.get("entities"), list):
        raise ValueError("Canonical StructureTree requires CW entities")
    items: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    refs: set[str] = set()
    complete_file_inventory = True

    def add(ref: str, surface: str, semantic: dict[str, Any]) -> None:
        if not isinstance(ref, str) or not ref or ref in refs:
            raise ValueError("Canonical comparison identity missing or duplicated")
        refs.add(ref)
        items.append({
            "ref": ref,
            "surface": surface,
            "semantic": copy.deepcopy(semantic),
            "canonical_semantic_authority": False,
            "evidence_kind": "derived_from_explicit_CW",
        })

    for entity in document["entities"]:
        if not isinstance(entity, dict):
            raise ValueError("CW Entity must be object")
        entity_ref = entity.get("id")
        if not isinstance(entity_ref,str) or not entity_ref:
            raise ValueError("CW Entity needs explicit id")
        if not entity_ref.startswith("#FILE:"):
            # No alternative family is forced into FILE correspondence.
            continue
        prop_index: dict[str,list[dict[str,Any]]] = {}
        for prop in entity.get("properties", []):
            if not isinstance(prop,dict):
                continue
            value=prop.get("value")
            if not isinstance(value,dict):
                continue
            data_type=value.get("data_type_ref")
            if prop.get("property_type_ref")=="data" and isinstance(data_type,str):
                prop_index.setdefault(data_type,[]).append(value)
        source=prop_index.get("source_path",[])
        languages=prop_index.get("language_id",[])
        if len(source)!=1 or len(languages)!=1 or not isinstance(source[0].get("value"),str) or not isinstance(languages[0].get("value"),str):
            complete_file_inventory=False
            warnings.append({
                "entity_ref":entity_ref,"kind":"source_metadata_missing_or_ambiguous",
            })
        add(entity_ref,"entity",{
            "kind":"observed_source_file",
            "source_path":source[0].get("value") if len(source)==1 else None,
            "language_id":languages[0].get("value") if len(languages)==1 else None,
        })
        for property in entity.get("properties", []):
            if not isinstance(property,dict) or property.get("property_type_ref")!="function":
                continue
            prop_ref=property.get("id")
            props=property.get("value",{}).get("properties")
            if not isinstance(props,dict):
                warnings.append({
                    "entity_ref":entity_ref,"property_ref":prop_ref,
                    "kind":"function_semantic_metadata_missing",
                })
                continue
            add("CW_FUNCTION::"+entity_ref+"::"+str(prop_ref),"function",{
                "kind":"observed_function",
                "qualified_name":props.get("qualified_name"),
                "parameters":copy.deepcopy(props.get("parameters",[])),
                "returns_annotation":props.get("returns_annotation"),
                "async":props.get("async"),
                "decomposition_state":props.get("decomposition_state"),
            })
            primitive=props.get("primitive_decomposition")
            if isinstance(primitive,dict):
                add("CW_LOGIC::"+entity_ref+"::"+str(prop_ref),
                    "function_logic",{
                        "kind":"observed_primitive_logic",
                        "primitive_set_ref":primitive.get("primitive_set_ref"),
                        "body":copy.deepcopy(primitive.get("body",[])),
                        "unresolved":copy.deepcopy(primitive.get("unresolved",[])),
                        "decomposition_state":primitive.get("decomposition_state"),
                    })
    return {
        "kind":"cic_cw_derived_structuretree",
        "version":"1.0.0",
        "items":items,
        "complete_surfaces":["entity"] if complete_file_inventory else [],
        "warnings":warnings,
        "summary":dict(sorted(Counter(item["surface"] for item in items).items())),
        "canonical_semantic_authority":False,
        "source_kind":"CW_derived_projection",
        "canonical_authority_remains_source_CW":True,
    }

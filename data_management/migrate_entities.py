#!/usr/bin/env python
"""
Migration script to populate Entity table from Patent data.
Extracts inventors and applicants from the JSON fields in Patent model
and creates Entity records with many-to-many relationships to patents.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from accounts.models import Patent, Entity
from django.db import transaction


def get_entity_name(inventor_or_applicant):
    """
    Extract a display name from inventor/applicant data.
    
    Args:
        inventor_or_applicant: dict with first_name, last_name, organization keys
        
    Returns:
        str: The name to use for the entity
    """
    # Check for organization first (applicants often have this)
    if inventor_or_applicant.get('organization'):
        return inventor_or_applicant['organization'].strip()
    
    # Otherwise use first_name + last_name
    first_name = inventor_or_applicant.get('first_name', '') or ''
    last_name = inventor_or_applicant.get('last_name', '') or ''
    
    full_name = f"{first_name} {last_name}".strip()
    return full_name if full_name else None


def migrate_entities():
    """
    Main migration function to populate Entity table from Patent data.
    """
    print("=" * 60)
    print("Starting Entity migration from Patent data")
    print("=" * 60)
    
    # Clear existing entities (optional - comment out if you want to keep existing)
    # Entity.objects.all().delete()
    # print("Cleared existing entities")
    
    # Get all patents with inventors or applicants
    patents = Patent.objects.filter(
        models.Q(inventors__isnull=False) | models.Q(applicants__isnull=False)
    ).distinct()
    
    total_patents = patents.count()
    print(f"\nFound {total_patents} patents with inventor or applicant data")
    
    # Track statistics
    stats = {
        'inventors_created': 0,
        'applicants_created': 0,
        'inventors_linked': 0,
        'applicants_linked': 0,
        'patents_processed': 0,
    }
    
    # Use bulk operations for efficiency
    entities_to_create = []
    entity_patent_relations = []  # (entity_name, entity_type, patent_id)
    
    # Track unique entities to avoid duplicates
    seen_entities = {}  # (name, entity_type) -> entity_id
    
    # Process each patent
    for patent in patents.iterator(chunk_size=500):
        stats['patents_processed'] += 1
        
        # Process inventors
        if patent.inventors:
            for inventor in patent.inventors:
                name = get_entity_name(inventor)
                if not name:
                    continue
                
                entity_key = (name, 'inventor')
                
                if entity_key not in seen_entities:
                    # Check if entity already exists in database
                    existing = Entity.objects.filter(name=name, entity_type='inventor').first()
                    if existing:
                        seen_entities[entity_key] = existing.entity_id
                    else:
                        entities_to_create.append(Entity(name=name, entity_type='inventor'))
                
                # Track the relation to be created
                entity_patent_relations.append((name, 'inventor', patent.patent_id))
        
        # Process applicants
        if patent.applicants:
            for applicant in patent.applicants:
                name = get_entity_name(applicant)
                if not name:
                    continue
                
                entity_key = (name, 'applicant')
                
                if entity_key not in seen_entities:
                    # Check if entity already exists in database
                    existing = Entity.objects.filter(name=name, entity_type='applicant').first()
                    if existing:
                        seen_entities[entity_key] = existing.entity_id
                    else:
                        entities_to_create.append(Entity(name=name, entity_type='applicant'))
                
                # Track the relation to be created
                entity_patent_relations.append((name, 'applicant', patent.patent_id))
        
        # Print progress every 5000 patents
        if stats['patents_processed'] % 5000 == 0:
            print(f"  Processed {stats['patents_processed']}/{total_patents} patents...")
    
    print(f"\nCreating {len(entities_to_create)} new entities...")
    
    # Bulk create entities (handle duplicates with ignore_conflicts)
    if entities_to_create:
        # Use update_or_create in batches to handle race conditions
        created_count = 0
        for entity in entities_to_create:
            obj, created = Entity.objects.get_or_create(
                name=entity.name,
                entity_type=entity.entity_type
            )
            if created:
                created_count += 1
                seen_entities[(entity.name, entity.entity_type)] = obj.entity_id
        
        print(f"  Created {created_count} new entities")
        stats['inventors_created'] = len([e for e in entities_to_create if e.entity_type == 'inventor'])
        stats['applicants_created'] = len([e for e in entities_to_create if e.entity_type == 'applicant'])
    
    # Now link entities to patents
    print("\nLinking entities to patents...")
    
    # Get all entities to build lookup
    all_entities = Entity.objects.all()
    entity_lookup = {(e.name, e.entity_type): e for e in all_entities}
    
    # Build patent lookup
    patent_lookup = {p.patent_id: p for p in Patent.objects.all()}
    
    # Link entities to patents
    links_created = 0
    for name, entity_type, patent_id in entity_patent_relations:
        entity = entity_lookup.get((name, entity_type))
        patent = patent_lookup.get(patent_id)
        
        if entity and patent:
            entity.patents.add(patent)
            links_created += 1
    
    print(f"  Created {links_created} entity-patent relationships")
    
    # Print final statistics
    print("\n" + "=" * 60)
    print("Migration Complete!")
    print("=" * 60)
    print(f"Patents processed: {stats['patents_processed']}")
    print(f"Total entities in database: {Entity.objects.count()}")
    print(f"  - Inventors: {Entity.objects.filter(entity_type='inventor').count()}")
    print(f"  - Applicants: {Entity.objects.filter(entity_type='applicant').count()}")
    print(f"Entity-patent relationships: {links_created}")
    
    return stats


if __name__ == '__main__':
    from django.db import models
    
    # Run the migration
    migrate_entities()
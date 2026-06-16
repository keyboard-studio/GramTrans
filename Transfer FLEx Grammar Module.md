# Transfer FLEx Grammar Module Design

# Problem statement:

When users work on a toy project either when testing FLExTrans or when getting parsing working, there’s no easy way to get all the grammar pieces from the toy project to the main project that will be used for production.

# Existing solution:

A user can export phonology grammar data from one project and import it to another project. That gets us part of the way there. I believe this takes care of the following items:

1. Phonemes  
2. Phonological Features  
3. Natural Classes  
4. Phonological Rules  
5. APRs?  
6. Environments? (phon rules and/or allomorphs) Same list?

# Big idea:

It would be nice to have a module that would transfer important grammar data from a toy project to another project. It would be great if it was interactive so the user could choose to only transfer some information.

Things we might want to transfer:

1. Check Writing Systems  
2. Gram Categories (Keep GOLD)  
3. Inflection Features\* (Keep GOLD)  
4. Custom Fields (especially the link custom field use for FLExTrans)  
5. Inflection Classes  
6. Stem Names  
7. Exception Features  
8. Variant Types (and associated inflection features)  
9. Complex Form Types  
10. Ad Hoc Rules  
11. Compound Rules  
12. Affixes\* (includes APRs and Allomorphs)  
13. Slots  
14. Templates\*  
    1. Add affixes to slots

Choosing to transfer some of the things above will automatically mean including other things. E.g. transferring templates might mean we transfer the affixes in that template. Transferring affixes might mean including all the features and classes associated.

It would be nice if FLEx itself would support this, but in the meantime we probably need to write our own module.

Flavor  
Flexlibs1 with C\# Fallback

## Main Window

1. Choose which of the grammar pieces to transfer  
2. Some choices will automatically select others  
   1. Perhaps this automatic selection could be deselected to get a more bare bones version  
3. Statistics, perhaps in the FlexTools window, about what was transferred  
4. Overwrite option?

## Affixes

1. Should include all allomorphs in the affix entry  
2. Should include APRs if not handled in FLEx’s export/import  
3. Should included all referenced items:  
   1. Inflection Features  
   2. Inflection Classes  
   3. Stem Names  
   4. Exception Features  
4. The user should be able choose which affixes to transfer

## Merging

### Phase 0 \- New

* Add new things even if duplicate  
* Tag new entries in Import Residue  
* No UI, just add everything  
* Update default vernacular (mapping)

### Phase 1 \- Overwrite

Overwrite intelligently?

- Try Guid  
- Fall back to fingerprint  
- UI Main Window to ask which pieces to transfer  
- Leave non-conflicting items  
- Dedup Custom Fields

### Phase 2 \- Proper Merging

* User prompted,   
* Accept merge, left, right, skip, other  
* Map the vernaculars (like SFM import)  
* Undoable

Architecture

* From Flextools,   
  * PyQT interface  
  * Preview Mode and Move Mode  
  * Overwrite in V1, Merge in V2 
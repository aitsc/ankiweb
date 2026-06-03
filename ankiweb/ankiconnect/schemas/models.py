"""Request models for the model (note type) actions (ankiweb/ankiconnect/actions/models.py)."""
from __future__ import annotations
from typing import Optional
from pydantic import Field
from ankiweb.ankiconnect.schemas._base import ACBaseModel


class ModelNamesParams(ACBaseModel):
    """List the names of all note types (models)."""


class ModelNamesAndIdsParams(ACBaseModel):
    """Map each note type name to its id."""


class ModelFieldNamesParams(ACBaseModel):
    """List the field names of a note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")


class ModelFieldDescriptionsParams(ACBaseModel):
    """List the per-field descriptions of a note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")


class ModelFieldFontsParams(ACBaseModel):
    """Map each field of a note type to its font and size."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")


class ModelTemplatesParams(ACBaseModel):
    """Map each template of a note type to its Front/Back content."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")


class ModelStylingParams(ACBaseModel):
    """Return the CSS styling of a note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")


class ModelFieldsOnTemplatesParams(ACBaseModel):
    """List which fields are referenced on the question/answer side of each template."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")


class FindModelsByIdParams(ACBaseModel):
    """Return the full model dicts for the given note type ids."""
    modelIds: list[int] = Field(default_factory=list, description="Note type ids.")


class FindModelsByNameParams(ACBaseModel):
    """Return the full model dicts for the given note type names."""
    modelNames: list[str] = Field(default_factory=list, description="Note type names.")


class ModelNameFromIdParams(ACBaseModel):
    """Return the name of a note type given its id."""
    modelId: Optional[int] = Field(default=None, description="Note type id.")


class CreateModelCardTemplate(ACBaseModel):
    """One card template specification for createModel."""
    Name: str = Field(default="", description="Template name, e.g. 'Card 1'.")
    Front: str = Field(default="", description="Front (question) HTML template.")
    Back: str = Field(default="", description="Back (answer) HTML template.")


class CreateModelParams(ACBaseModel):
    """Create a new note type (model)."""
    modelName: Optional[str] = Field(default=None, description="Name for the new note type.")
    inOrderFields: list[str] = Field(default_factory=list,
                                     description="Field names, in order.")
    cardTemplates: list[CreateModelCardTemplate] = Field(
        default_factory=list, description="Card templates for the new note type.")
    css: Optional[str] = Field(default=None,
                               description="Optional CSS; defaults to Anki's builtin CSS.")
    isCloze: bool = Field(default=False, description="Create as a Cloze note type when True.")


class UpdateModelTemplatesModel(ACBaseModel):
    """The model wrapper accepted by updateModelTemplates."""
    name: Optional[str] = Field(default=None, description="Existing note type name.")
    templates: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="Template name -> {'Front': html, 'Back': html}; omitted sides left unchanged.")


class UpdateModelTemplatesParams(ACBaseModel):
    """Modify the templates of an existing note type."""
    model: Optional[UpdateModelTemplatesModel] = Field(
        default=None, description="Model wrapper with name and templates to update.")


class UpdateModelStylingModel(ACBaseModel):
    """The model wrapper accepted by updateModelStyling."""
    name: Optional[str] = Field(default=None, description="Existing note type name.")
    css: str = Field(default="", description="New CSS styling for the note type.")


class UpdateModelStylingParams(ACBaseModel):
    """Modify the CSS styling of an existing note type."""
    model: Optional[UpdateModelStylingModel] = Field(
        default=None, description="Model wrapper with name and css.")


class FindAndReplaceInModelsParams(ACBaseModel):
    """Find and replace text across a note type's templates and CSS."""
    modelName: Optional[str] = Field(
        default=None, description="Note type name; falsy means all note types.")
    findText: Optional[str] = Field(default=None, description="Text to find.")
    replaceText: Optional[str] = Field(default=None, description="Replacement text.")
    front: bool = Field(default=True, description="Search question-side templates.")
    back: bool = Field(default=True, description="Search answer-side templates.")
    css: bool = Field(default=True, description="Search the CSS styling.")


class ModelTemplateAddTemplate(ACBaseModel):
    """The template specification accepted by modelTemplateAdd."""
    Name: Optional[str] = Field(default=None, description="Template name.")
    Front: Optional[str] = Field(default=None, description="Front (question) HTML template.")
    Back: Optional[str] = Field(default=None, description="Back (answer) HTML template.")


class ModelTemplateAddParams(ACBaseModel):
    """Add (or update) a template on an existing note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")
    template: Optional[ModelTemplateAddTemplate] = Field(
        default=None, description="Template to add, with Name/Front/Back.")


class ModelTemplateRemoveParams(ACBaseModel):
    """Remove a template from a note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")
    templateName: Optional[str] = Field(default=None, description="Template name to remove.")


class ModelTemplateRenameParams(ACBaseModel):
    """Rename a template of a note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")
    oldTemplateName: Optional[str] = Field(default=None, description="Current template name.")
    newTemplateName: Optional[str] = Field(default=None, description="New template name.")


class ModelTemplateRepositionParams(ACBaseModel):
    """Move a template to a new position within a note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")
    templateName: Optional[str] = Field(default=None, description="Template name to move.")
    index: Optional[int] = Field(default=None, description="New zero-based position.")


class ModelFieldAddParams(ACBaseModel):
    """Add a field to a note type, optionally at a position."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")
    fieldName: Optional[str] = Field(default=None, description="Name of the field to add.")
    index: Optional[int] = Field(default=None, description="Optional zero-based position.")


class ModelFieldRemoveParams(ACBaseModel):
    """Remove a field from a note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")
    fieldName: Optional[str] = Field(default=None, description="Name of the field to remove.")


class ModelFieldRenameParams(ACBaseModel):
    """Rename a field of a note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")
    oldFieldName: Optional[str] = Field(default=None, description="Current field name.")
    newFieldName: Optional[str] = Field(default=None, description="New field name.")


class ModelFieldRepositionParams(ACBaseModel):
    """Move a field to a new position within a note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")
    fieldName: Optional[str] = Field(default=None, description="Field name to move.")
    index: Optional[int] = Field(default=None, description="New zero-based position.")


class ModelFieldSetFontParams(ACBaseModel):
    """Set the editor font of a field on a note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")
    fieldName: Optional[str] = Field(default=None, description="Field name.")
    font: Optional[str] = Field(default=None, description="Font family name.")


class ModelFieldSetFontSizeParams(ACBaseModel):
    """Set the editor font size of a field on a note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")
    fieldName: Optional[str] = Field(default=None, description="Field name.")
    fontSize: Optional[int] = Field(default=None, description="Font size in points.")


class ModelFieldSetDescriptionParams(ACBaseModel):
    """Set the description of a field on a note type."""
    modelName: Optional[str] = Field(default=None, description="Note type name.")
    fieldName: Optional[str] = Field(default=None, description="Field name.")
    description: Optional[str] = Field(default=None, description="Field description text.")

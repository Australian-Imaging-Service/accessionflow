import os
import typing as ty

import pytest
from fileformats.application import Json, Yaml
from fileformats.core import Loaded, extra_implementation, validated_property
from fileformats.generic import Directory, File
from fileformats.medimage import MedicalImagingData

from accessionflow.model.accession import recipe_formats_for


class RecipeYamlOrJson(File, MedicalImagingData):
    ext = ".yaml-or-json"


class RecipeJson(File, MedicalImagingData):
    ext = ".json-only"


class RecipeYaml(File, MedicalImagingData):
    ext = ".yaml-only"


class NoRecipe(File, MedicalImagingData):
    ext = ".no-recipe"


class Unimplemented(File, MedicalImagingData):
    """May contain PHI but has no deidentify implementation"""

    ext = ".unimplemented"


@extra_implementation(MedicalImagingData.deidentify)
def yaml_or_json_deidentify(
    fileset: RecipeYamlOrJson,
    out_dir: os.PathLike[str],
    recipe: Loaded[Yaml] | Loaded[Json] | None = None,
    **kwargs: ty.Any,
) -> RecipeYamlOrJson:
    raise NotImplementedError


@extra_implementation(MedicalImagingData.deidentify)
def json_deidentify(
    fileset: RecipeJson,
    out_dir: os.PathLike[str],
    recipe: Loaded[Json] | None = None,
    **kwargs: ty.Any,
) -> RecipeJson:
    raise NotImplementedError


@extra_implementation(MedicalImagingData.deidentify)
def yaml_deidentify(
    fileset: RecipeYaml,
    out_dir: os.PathLike[str],
    recipe: Loaded[Yaml] | None = None,
    **kwargs: ty.Any,
) -> RecipeYaml:
    raise NotImplementedError


@extra_implementation(MedicalImagingData.deidentify)
def no_recipe_deidentify(
    fileset: NoRecipe,
    out_dir: os.PathLike[str],
    recipe: None = None,
    **kwargs: ty.Any,
) -> NoRecipe:
    raise NotImplementedError


class NestedCommon(Directory, MedicalImagingData):
    contains_phi = "nested"

    @validated_property
    def yaml_or_json(self) -> list[RecipeYamlOrJson]:
        raise NotImplementedError

    @validated_property
    def json(self) -> RecipeJson | None:
        raise NotImplementedError

    @validated_property
    def no_recipe(self) -> NoRecipe:
        raise NotImplementedError

    @validated_property
    def plain(self) -> File:
        raise NotImplementedError


class NestedNoRecipe(Directory, MedicalImagingData):
    contains_phi = "nested"

    @validated_property
    def no_recipe(self) -> dict[str, NoRecipe]:
        raise NotImplementedError

    @validated_property
    def plain(self) -> File:
        raise NotImplementedError


class NestedIncompatible(Directory, MedicalImagingData):
    contains_phi = "nested"

    @validated_property
    def json(self) -> RecipeJson:
        raise NotImplementedError

    @validated_property
    def yaml(self) -> RecipeYaml:
        raise NotImplementedError


class NestedUnimplemented(Directory, MedicalImagingData):
    contains_phi = "nested"

    @validated_property
    def unimplemented(self) -> Unimplemented:
        raise NotImplementedError


class NestedTwoLevels(Directory, MedicalImagingData):
    contains_phi = "nested"

    @validated_property
    def nested(self) -> dict[str, NestedCommon]:
        raise NotImplementedError

    @validated_property
    def yaml_or_json(self) -> RecipeYamlOrJson:
        raise NotImplementedError


def test_recipe_formats_registered():
    assert recipe_formats_for(RecipeYamlOrJson) == [Yaml, Json]
    assert recipe_formats_for(NoRecipe) is None


def test_recipe_formats_unimplemented():
    with pytest.raises(NotImplementedError, match="Unimplemented"):
        recipe_formats_for(Unimplemented)


def test_recipe_formats_nested_common():
    # Only the formats accepted by all nested formats that take a recipe, in the order
    # of preference of the first of them, ignoring ones that don't take a recipe or
    # don't contain PHI
    assert recipe_formats_for(NestedCommon) == [Json]


def test_recipe_formats_nested_no_recipe():
    assert recipe_formats_for(NestedNoRecipe) is None


def test_recipe_formats_nested_two_levels():
    assert recipe_formats_for(NestedTwoLevels) == [Json]


def test_recipe_formats_nested_incompatible():
    with pytest.raises(TypeError, match="common recipe format"):
        recipe_formats_for(NestedIncompatible)


def test_recipe_formats_nested_unimplemented():
    with pytest.raises(NotImplementedError, match="Unimplemented"):
        recipe_formats_for(NestedUnimplemented)

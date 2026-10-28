"""Detecção de vídeo movido, renomeado ou alterado (US-27 RN04, Cenário 3)."""

from __future__ import annotations

import shutil

import pytest

from barnes.io.video import FileStatus, compute_content_hash, verify_video_file


@pytest.fixture
def catalogued(make_mp4):
    """Um vídeo como foi catalogado: caminho, hash e tamanho registrados."""
    path = make_mp4("trial_01.mp4", frame_count=12)
    return path, compute_content_hash(path), path.stat().st_size


def test_unchanged_file_is_ok(catalogued):
    path, digest, size = catalogued
    check = verify_video_file(path, digest, expected_size=size)
    assert check.status is FileStatus.OK
    assert not check.diverges


def test_moved_file_is_found_in_search_dir_and_flagged(catalogued, tmp_path):
    path, digest, size = catalogued
    destination = tmp_path / "arquivo_morto"
    destination.mkdir()
    moved = shutil.move(path, destination / path.name)

    check = verify_video_file(path, digest, expected_size=size, search_dirs=[destination])

    assert check.status is FileStatus.MOVIDO
    assert check.found_at == moved
    assert check.diverges
    assert str(moved) in check.describe()


def test_renamed_file_in_same_folder_is_flagged_as_moved(catalogued):
    path, digest, size = catalogued
    renamed = path.rename(path.with_name("renomeado.mp4"))

    check = verify_video_file(path, digest, expected_size=size)

    assert check.status is FileStatus.MOVIDO
    assert check.found_at == renamed


def test_replaced_content_at_same_path_is_altered(catalogued, make_mp4):
    path, digest, size = catalogued
    other = make_mp4("outro.mp4", frame_count=20)
    shutil.copyfile(other, path)

    check = verify_video_file(path, digest, expected_size=size)

    assert check.status is FileStatus.ALTERADO
    assert check.actual_hash != digest
    assert check.diverges


def test_missing_file_not_found_anywhere(catalogued):
    path, digest, size = catalogued
    path.unlink()
    check = verify_video_file(path, digest, expected_size=size)
    assert check.status is FileStatus.AUSENTE
    assert check.diverges


def test_other_video_with_different_content_is_not_mistaken_for_moved(catalogued, make_mp4):
    path, digest, size = catalogued
    make_mp4("vizinho.mp4", frame_count=30)
    path.unlink()
    assert verify_video_file(path, digest, expected_size=size).status is FileStatus.AUSENTE


def test_cheap_check_detects_size_change_without_hashing(catalogued, make_mp4):
    path, digest, size = catalogued
    shutil.copyfile(make_mp4("maior.mp4", frame_count=40), path)
    check = verify_video_file(path, digest, expected_size=size, verify_hash=False)
    assert check.status is FileStatus.ALTERADO
    assert check.actual_hash is None


def test_cheap_check_with_matching_size_is_only_present(catalogued):
    path, digest, size = catalogued
    check = verify_video_file(path, digest, expected_size=size, verify_hash=False)
    assert check.status is FileStatus.PRESENTE
    assert not check.diverges

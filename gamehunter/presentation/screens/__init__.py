"""Экраны Telegram-бота и их сборка (контейнер экранов).

Экраны соответствуют карте перемещения по экранам из документации проекта
(``docs/05_*.md``): каждому номеру экрана — свой класс.
"""

from __future__ import annotations

from dataclasses import dataclass

from gamehunter.domain.services import GameService, LibraryService, ProfileService
from gamehunter.presentation.gateway import TelegramGateway
from gamehunter.presentation.screens.franchise import (
    FranchiseGamesScreen,
    FranchiseInputScreen,
    FranchiseListScreen,
)
from gamehunter.presentation.screens.library import (
    FavoritesScreen,
    PlayedListScreen,
    PlayedInfoScreen,
    ReviewInputScreen,
)
from gamehunter.presentation.screens.menu import MainMenuScreen, StartScreen
from gamehunter.presentation.screens.picking import (
    GameCardScreen,
    GameListScreen,
    GenrePickingScreen,
)
from gamehunter.presentation.screens.profile import (
    AgeInputScreen,
    ProfileGenresScreen,
    ProfilePlatformsScreen,
    ProfileScreen,
    RegionInputScreen,
)
from gamehunter.presentation.state import StateStorage


@dataclass(frozen=True)
class ScreenContainer:
    """Набор всех экранов бота."""

    start: StartScreen                          # Экран 1
    main_menu: MainMenuScreen                   # Экран 2
    genre_picking: GenrePickingScreen           # Экран 3
    game_list: GameListScreen                   # Экран 4
    game_card: GameCardScreen                   # Экран 5
    franchise_input: FranchiseInputScreen       # Экран 6
    franchise_list: FranchiseListScreen         # Экран 7
    franchise_games: FranchiseGamesScreen       # Экран 8
    profile: ProfileScreen                      # Экран 9
    age_input: AgeInputScreen                   # Экран 9а
    profile_genres: ProfileGenresScreen         # Экран 9б
    profile_platforms: ProfilePlatformsScreen   # Экран 9в
    region_input: RegionInputScreen             # Экран 9г
    played_list: PlayedListScreen               # Экран 10
    played_info: PlayedInfoScreen               # Экран 11
    review_input: ReviewInputScreen             # Экран 11а
    favorites: FavoritesScreen                  # Экран 12


def build_screens(
    gateway: TelegramGateway,
    storage: StateStorage,
    game_service: GameService,
    profile_service: ProfileService,
    library_service: LibraryService,
) -> ScreenContainer:
    """Создаёт экраны и связывает их с сервисами (композиция без глобальных объектов)."""
    start_screen = StartScreen(gateway, storage)
    main_menu_screen = MainMenuScreen(gateway, storage)

    # --- подбор игр по интересам (Экраны 3–5) ---
    game_list_screen = GameListScreen(
        gateway, storage, game_service, profile_service, library_service
    )
    genre_picking_screen = GenrePickingScreen(
        gateway, storage, game_service, profile_service, game_list_screen
    )
    game_card_screen = GameCardScreen(
        gateway, storage, game_service, profile_service, library_service
    )

    # --- поиск по франшизе (Экраны 6–8) ---
    franchise_input_screen = FranchiseInputScreen(gateway, storage)
    franchise_list_screen = FranchiseListScreen(
        gateway, storage, game_service, franchise_input_screen
    )
    franchise_input_screen.attach_list_screen(franchise_list_screen)
    franchise_games_screen = FranchiseGamesScreen(gateway, storage, game_service)

    # --- анкета (Экран 9 и его режимы) ---
    profile_screen = ProfileScreen(gateway, storage, profile_service)
    age_input_screen = AgeInputScreen(gateway, storage, profile_service, profile_screen)
    profile_genres_screen = ProfileGenresScreen(
        gateway, storage, game_service, profile_service, profile_screen
    )
    profile_platforms_screen = ProfilePlatformsScreen(
        gateway, storage, game_service, profile_service, profile_screen
    )
    region_input_screen = RegionInputScreen(
        gateway, storage, profile_service, profile_screen
    )

    # --- библиотека пользователя (Экраны 10–12) ---
    played_list_screen = PlayedListScreen(gateway, storage, library_service)
    played_info_screen = PlayedInfoScreen(
        gateway, storage, library_service, played_list_screen
    )
    review_input_screen = ReviewInputScreen(
        gateway, storage, library_service, played_info_screen
    )
    favorites_screen = FavoritesScreen(gateway, storage, library_service)

    return ScreenContainer(
        start=start_screen,
        main_menu=main_menu_screen,
        genre_picking=genre_picking_screen,
        game_list=game_list_screen,
        game_card=game_card_screen,
        franchise_input=franchise_input_screen,
        franchise_list=franchise_list_screen,
        franchise_games=franchise_games_screen,
        profile=profile_screen,
        age_input=age_input_screen,
        profile_genres=profile_genres_screen,
        profile_platforms=profile_platforms_screen,
        region_input=region_input_screen,
        played_list=played_list_screen,
        played_info=played_info_screen,
        review_input=review_input_screen,
        favorites=favorites_screen,
    )


__all__ = [
    "AgeInputScreen",
    "FavoritesScreen",
    "FranchiseGamesScreen",
    "FranchiseInputScreen",
    "FranchiseListScreen",
    "GameCardScreen",
    "GameListScreen",
    "GenrePickingScreen",
    "MainMenuScreen",
    "PlayedListScreen",
    "PlayedInfoScreen",
    "ProfileGenresScreen",
    "ProfilePlatformsScreen",
    "ProfileScreen",
    "RegionInputScreen",
    "ReviewInputScreen",
    "ScreenContainer",
    "StartScreen",
    "build_screens",
]

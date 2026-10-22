import json
import random
from pathlib import Path

import pygame


# All game code stays here. Only saved scores use a separate data file.
BASE_DIR = Path(__file__).resolve().parent
LEADERBOARD_FILE = BASE_DIR / 'leaderboard.json'
WIDTH, HEIGHT = 500, 500
FPS = 120
LANES = (150, 250, 350)
PLAYER_Y = 400
CARS_PER_STAGE = 10
WHITE = (255, 255, 255)
YELLOW = (255, 232, 0)
RED = (200, 0, 0)

# Add more environments here. They repeat after the last one.
# name, ground color, road color, lane-marker color
ENVIRONMENTS = (
    ('Grassland', (76, 208, 56), (0, 0, 0), WHITE),
    ('Desert', (224, 186, 112), (70, 60, 50), WHITE),
    ('Sunset', (165, 97, 68), (48, 40, 48), (255, 222, 170)),
    ('Snow', (220, 235, 240), (65, 75, 85), WHITE),
    ('Night', (22, 40, 37), (12, 15, 25), (185, 195, 215)),
)


def stage_for_score(score):
    return score // CARS_PER_STAGE + 1


def load_leaderboard(path=LEADERBOARD_FILE):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    entries = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        score, stage = entry.get('score'), entry.get('stage')
        name = entry.get('name')
        if (isinstance(name, str) and type(score) is int and score >= 0
                and type(stage) is int and stage > 0):
            entries.append({'name': name[:12] or 'Player',
                            'score': score, 'stage': stage})
    return sorted(entries, key=lambda entry: entry['score'], reverse=True)[:10]


def save_score(entries, name, score, path=LEADERBOARD_FILE):
    updated = entries + [{'name': name, 'score': score,
                          'stage': stage_for_score(score)}]
    updated.sort(key=lambda entry: entry['score'], reverse=True)
    updated = updated[:10]
    # Replace atomically so an interrupted write preserves the old save.
    temporary = path.with_suffix('.tmp')
    try:
        temporary.write_text(json.dumps(updated, indent=2), encoding='utf-8')
        temporary.replace(path)
    except OSError:
        return updated, 'Scores could not be saved to disk.'
    return updated, ''


class Vehicle(pygame.sprite.Sprite):
    def __init__(self, image, x, y):
        super().__init__()
        scale = 45 / image.get_width()
        self.image = pygame.transform.scale(
            image, (45, max(1, round(image.get_height() * scale))))
        self.rect = self.image.get_rect(center=(x, y))
        self.x, self.y = float(x), float(y)

    def update(self, dt, speed, player, vehicles):
        self.y += speed * FPS * dt
        self.rect.center = (round(self.x), round(self.y))


class EnemyVehicle(Vehicle):
    """An opponent that picks adjacent lanes and steers toward the player."""

    def __init__(self, image, x, y):
        super().__init__(image, x, y)
        self.target_lane = x
        self.decision_timer = random.uniform(0.7, 1.4)

    def lane_is_clear(self, lane, vehicles):
        # Reserve the whole lane-change corridor plus a following gap.
        corridor = self.rect.union(self.rect.move(lane - self.rect.centerx, 0))
        corridor.inflate_ip(20, 150)
        return not any(other is not self and corridor.colliderect(other.rect)
                       for other in vehicles)

    def update(self, dt, speed, player, vehicles):
        self.decision_timer -= dt
        # Stop choosing lanes near the player, leaving time to dodge.
        if (self.decision_timer <= 0 and self.x == self.target_lane
                and self.rect.bottom < player.rect.top - 120):
            self.decision_timer = random.uniform(0.9, 1.7)
            current = LANES.index(self.target_lane)
            choices = [lane for index, lane in enumerate(LANES)
                       if abs(index - current) == 1
                       and self.lane_is_clear(lane, vehicles)]
            if choices:
                self.target_lane = min(
                    choices, key=lambda lane: abs(lane - player.rect.centerx))

        if self.x != self.target_lane:
            if self.lane_is_clear(self.target_lane, vehicles):
                step = 180 * dt
                distance = self.target_lane - self.x
                self.x += max(-step, min(step, distance))
            else:
                self.target_lane = min(LANES, key=lambda lane: abs(lane - self.x))
        super().update(dt, speed, player, vehicles)


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption('Car Game')
    clock = pygame.time.Clock()
    font = pygame.font.Font(pygame.font.get_default_font(), 16)
    small_font = pygame.font.Font(pygame.font.get_default_font(), 13)
    title_font = pygame.font.Font(pygame.font.get_default_font(), 24)

    def label(text, x, y, color=WHITE, small=False, centered=False):
        surface = (small_font if small else font).render(text, True, color)
        rect = surface.get_rect()
        if centered:
            rect.midtop = (x, y)
        else:
            rect.topleft = (x, y)
        screen.blit(surface, rect)

    def panel(title):
        overlay = pygame.Surface((460, 420), pygame.SRCALPHA)
        overlay.fill((15, 20, 25, 235))
        screen.blit(overlay, (20, 40))
        text = title_font.render(title, True, WHITE)
        screen.blit(text, text.get_rect(midtop=(WIDTH // 2, 56)))

    def draw_scores(entries, top, limit=10):
        label('Rank   Driver', 45, top, small=True)
        label('Score', 318, top, small=True)
        label('Stage', 399, top, small=True)
        if not entries:
            label('No scores yet. Finish your first run!', WIDTH // 2,
                  top + 32, centered=True, small=True)
        for index, entry in enumerate(entries[:limit]):
            y = top + 25 + index * 25
            label(f"{index + 1:>2}.    {entry['name']}", 45, y, small=True)
            label(str(entry['score']), 330, y, small=True)
            label(str(entry['stage']), 415, y, small=True)

    # Reuse the original artwork. Drop extra traffic PNGs in images/.
    image_dir = BASE_DIR / 'images'
    player_image = pygame.image.load(str(image_dir / 'car.png')).convert_alpha()
    vehicle_images = [pygame.image.load(str(path)).convert_alpha()
                      for path in sorted(image_dir.glob('*.png'))
                      if path.name.lower() not in ('car.png', 'crash.png')]
    if not vehicle_images:
        vehicle_images = [player_image]
    crash = pygame.image.load(str(image_dir / 'crash.png')).convert_alpha()
    player = Vehicle(player_image, LANES[1], PLAYER_Y)
    vehicles = pygame.sprite.Group()
    leaderboard = load_leaderboard()
    player_name = ''
    state = 'name'
    show_leaderboard = False
    score = 0
    speed = 2
    lane_marker_y = 0
    stage_notice = 3.0
    saved_run = False
    save_error = ''

    def record_run():
        nonlocal leaderboard, saved_run, save_error
        if not saved_run:
            leaderboard, save_error = save_score(
                leaderboard, player_name or 'Player', score)
            saved_run = True

    running = True
    try:
        while running:
            dt = min(clock.tick(FPS) / 1000.0, 0.05)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break
                if event.type != pygame.KEYDOWN:
                    continue

                if state == 'name':
                    if event.key == pygame.K_RETURN:
                        player_name = player_name.strip() or 'Player'
                        state = 'playing'
                    elif event.key == pygame.K_BACKSPACE:
                        player_name = player_name[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.unicode.isprintable() and len(player_name) < 12:
                        player_name += event.unicode
                    continue

                if event.key == pygame.K_l:
                    show_leaderboard = not show_leaderboard
                    continue
                if show_leaderboard:
                    if event.key == pygame.K_ESCAPE:
                        show_leaderboard = False
                    continue
                if event.key == pygame.K_ESCAPE:
                    running = False
                    break

                if state == 'gameover':
                    if event.key in (pygame.K_y, pygame.K_RETURN):
                        vehicles.empty()
                        player.x, player.y = LANES[1], PLAYER_Y
                        player.rect.center = (LANES[1], PLAYER_Y)
                        score, speed, lane_marker_y = 0, 2, 0
                        stage_notice = 3.0
                        saved_run = False
                        state = 'playing'
                    elif event.key == pygame.K_n:
                        running = False
                    continue

                lane_index = LANES.index(player.rect.centerx)
                if event.key in (pygame.K_LEFT, pygame.K_a) and lane_index > 0:
                    player.rect.centerx = LANES[lane_index - 1]
                elif event.key in (pygame.K_RIGHT, pygame.K_d) and lane_index < 2:
                    player.rect.centerx = LANES[lane_index + 1]
                # Check every lane change so rapid keys cannot skip collisions.
                if pygame.sprite.spritecollideany(player, vehicles):
                    state = 'gameover'
                    record_run()

            if not running:
                break

            if state == 'playing' and not show_leaderboard:
                previous_stage = stage_for_score(score)
                lane_marker_y = (lane_marker_y + speed * 2 * FPS * dt) % 100
                stage_notice = max(0, stage_notice - dt)

                # Two vehicles at a time leaves a lane available to dodge.
                if len(vehicles) < 2 and all(
                        vehicle.rect.top >= vehicle.rect.height * 1.5
                        for vehicle in vehicles):
                    lane = random.choice(LANES)
                    image = random.choice(vehicle_images)
                    enemy_chance = min(0.35 + (previous_stage - 1) * 0.1, 0.75)
                    vehicle_type = (EnemyVehicle if random.random() < enemy_chance
                                    else Vehicle)
                    vehicles.add(vehicle_type(image, lane, -HEIGHT // 2))

                vehicles.update(dt, speed, player, vehicles)
                if pygame.sprite.spritecollideany(player, vehicles):
                    state = 'gameover'
                    record_run()
                else:
                    for vehicle in list(vehicles):
                        if vehicle.rect.top >= HEIGHT:
                            vehicle.kill()
                            score += 1
                    speed = min(2 + score // 5, 12)
                    if stage_for_score(score) != previous_stage:
                        stage_notice = 3.0

            stage = stage_for_score(score)
            name, ground, road, markers = ENVIRONMENTS[(stage - 1) % len(ENVIRONMENTS)]
            screen.fill(ground)
            pygame.draw.rect(screen, road, (100, 0, 300, HEIGHT))
            pygame.draw.rect(screen, YELLOW, (95, 0, 10, HEIGHT))
            pygame.draw.rect(screen, YELLOW, (395, 0, 10, HEIGHT))
            for y in range(-100, HEIGHT, 100):
                for lane_x in (195, 295):
                    pygame.draw.rect(screen, markers, (lane_x, y + lane_marker_y, 10, 50))
            vehicles.draw(screen)
            for vehicle in vehicles:
                if isinstance(vehicle, EnemyVehicle):
                    pygame.draw.rect(screen, RED,
                                     (vehicle.rect.centerx - 13, vehicle.rect.top - 16, 26, 15))
                    label('AI', vehicle.rect.centerx, vehicle.rect.top - 15,
                          small=True, centered=True)
            screen.blit(player.image, player.rect)

            # Dark backing keeps the original sidebar readable in snow.
            pygame.draw.rect(screen, (25, 30, 35), (4, 335, 87, 155))
            label('Score', 10, 345, small=True)
            label(str(score), 10, 363)
            label('Best', 10, 389, small=True)
            label(str(max(score, leaderboard[0]['score'] if leaderboard else 0)), 10, 407)
            label('L: Board', 10, 438, small=True)
            label('Stage ' + str(stage), 10, 465, small=True)
            if state == 'playing' and stage_notice > 0 and not show_leaderboard:
                pygame.draw.rect(screen, (25, 30, 35), (105, 15, 290, 58))
                label(f'Stage {stage}: {name}', WIDTH // 2, 23, centered=True)
                remaining = CARS_PER_STAGE - score % CARS_PER_STAGE
                label(f'Next stage in {remaining} cars', WIDTH // 2, 48,
                      small=True, centered=True)

            if state == 'name':
                panel('Car Game')
                label('Enter your name for the leaderboard:', WIDTH // 2, 120,
                      centered=True)
                label(player_name + '_', WIDTH // 2, 160, YELLOW, centered=True)
                label('Enter: start   |   Arrows / A D: steer', WIDTH // 2,
                      225, centered=True, small=True)
                label('L: leaderboard (pauses the game)', WIDTH // 2, 255,
                      centered=True, small=True)
                label('Red AI cars change lanes. Avoid all cars!', WIDTH // 2,
                      300, centered=True, small=True)
                label('Pass 10 cars per stage. Desert is stage 2.', WIDTH // 2,
                      335, centered=True, small=True)
            elif show_leaderboard:
                panel('Leaderboard - Top 10')
                draw_scores(leaderboard, 100)
                label('L / Esc: return', WIDTH // 2, 414, centered=True)
            elif state == 'gameover':
                crash_rect = crash.get_rect(center=(player.rect.centerx, player.rect.top))
                screen.blit(crash, crash_rect)
                panel('Game over')
                label(f'{player_name}: {score} points | Stage {stage}', WIDTH // 2,
                      96, centered=True)
                label('Leaderboard - Top 5', WIDTH // 2, 130, centered=True)
                draw_scores(leaderboard, 164, limit=5)
                label('Y / Enter: play again   N: quit', WIDTH // 2, 363,
                      centered=True, small=True)
                label('L: full leaderboard', WIDTH // 2, 390, centered=True, small=True)
                if save_error:
                    label(save_error, WIDTH // 2, 428, YELLOW,
                          centered=True, small=True)
            pygame.display.flip()
    finally:
        # Closing a live run also preserves its earned score, once only.
        if state == 'playing' and score > 0:
            record_run()
        pygame.quit()


if __name__ == '__main__':
    main()

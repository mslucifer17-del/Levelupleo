import math

class LevelSystem:
    def __init__(self):
        self.base_xp = 100  # XP needed for level 1
        self.multiplier = 1.5  # Exponential growth factor
    
    def xp_for_level(self, level):
        """Calculate total XP required for a specific level"""
        if level <= 0:
            return 0
        if level == 1:
            return self.base_xp
        
        # Progressive system as requested
        if level <= 10:
            # Levels 1-10: 10 messages per level
            return level * 10 * 10  # Assuming 1 message = 10 XP average
        elif level <= 25:
            # Levels 11-25: 25 messages per level
            base = 10 * 10 * 10  # XP for level 10
            additional = (level - 10) * 25 * 10
            return base + additional
        elif level <= 50:
            # Levels 26-50: 50 messages per level
            base = 10 * 10 * 10 + 15 * 25 * 10  # XP for level 25
            additional = (level - 25) * 50 * 10
            return base + additional
        else:
            # Levels 51-100+: 100 messages per level
            base = 10 * 10 * 10 + 15 * 25 * 10 + 25 * 50 * 10  # XP for level 50
            additional = (level - 50) * 100 * 10
            return base + additional
    
    def calculate_level(self, total_xp):
        """Calculate level from total XP"""
        level = 0
        while self.xp_for_level(level + 1) <= total_xp:
            level += 1
        return level
    
    def xp_to_next_level(self, current_xp, current_level):
        """Calculate XP needed for next level"""
        next_level_xp = self.xp_for_level(current_level + 1)
        return next_level_xp - current_xp

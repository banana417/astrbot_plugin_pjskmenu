import os
import random
import asyncio
import logging
from pathlib import Path
from PIL import Image
from datetime import datetime
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp

# 日志配置
logger = logging.getLogger("pjskmenu")
logger.setLevel(logging.INFO)

class PJSKMenuGame:
    """猜卡面游戏实例"""
    def __init__(self, group_id: str, character: str, image_path: str, crop_path: str):
        self.group_id = group_id
        self.character = character
        self.image_path = image_path
        self.crop_path = crop_path
        self.start_time = datetime.now()
        self.is_active = True

    def is_correct(self, guess: str, aliases: dict) -> bool:
        """检查答案是否正确"""
        if guess == self.character:
            return True
        
        # 检查别名
        for alias in aliases.get(self.character, []):
            if guess == alias:
                return True
        
        return False

@register("pjskmenu", "bunan417", "初音未来缤纷舞台猜卡面游戏", "1.0.0")
class PJSKMenuPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.games = {}  # {group_id: PJSKMenuGame}
        self.aliases = config.get("answer_aliases", {})
        self.whitelist = [str(gid) for gid in config.get("group_whitelist", [])]
        
        # 创建资源目录
        self.plugin_dir = Path(__file__).parent.resolve()
        self.menu_dir = self.plugin_dir / "menu"
        self.menu_dir.mkdir(exist_ok=True)
        
        # 加载卡面图片
        self.card_images = self.load_card_images()
        logger.info(f"Loaded {len(self.card_images)} card images")

    def load_card_images(self) -> list:
        """加载所有卡面图片路径"""
        return [
            (f.stem, str(f))
            for f in self.menu_dir.glob("*")
            if f.is_file() and f.suffix.lower() in [".jpg", ".jpeg", ".png"]
        ]

    async def start_game(self, event: AstrMessageEvent):
        """开始新游戏"""
        group_id = event.get_group_id()
        
        # 白名单验证
        if group_id not in self.whitelist:
            logger.info(f"Group {group_id} not in whitelist")
            await self.context.send_message(
                unified_msg_origin=f"group_{group_id}",
                chain=[Comp.Plain("本群未开通猜卡面游戏功能")]
            )
            return
        
        # 游戏状态检查
        if group_id in self.games:
            logger.info(f"Game already in progress in group {group_id}")
            await self.context.send_message(
                unified_msg_origin=f"group_{group_id}",
                chain=[Comp.Plain("当前已有游戏在进行中，请稍后再试")]
            )
            return
        
        # 随机选择卡面
        if not self.card_images:
            logger.error("No card images available")
            await self.context.send_message(
                unified_msg_origin=f"group_{group_id}",
                chain=[Comp.Plain("游戏资源加载失败，请联系管理员")]
            )
            return
        
        character, image_path = random.choice(self.card_images)
        
        # 创建裁剪图
        crop_path = await self.create_crop_image(image_path)
        if not crop_path:
            await self.context.send_message(
                unified_msg_origin=f"group_{group_id}",
                chain=[Comp.Plain("图片处理失败，请重试")]
            )
            return
        
        # 创建游戏实例
        game = PJSKMenuGame(group_id, character, image_path, crop_path)
        self.games[group_id] = game
        
        # 发送裁剪图
        await self.context.send_message(
            unified_msg_origin=f"group_{group_id}",
            chain=[Comp.Image.fromFileSystem(crop_path)]
        )
        logger.info(f"Game started in group {group_id} for {character}")
        
        # 设置30秒超时
        asyncio.create_task(self.game_timeout(group_id))

    async def create_crop_image(self, image_path: str) -> str:
        """创建裁剪图"""
        try:
            with Image.open(image_path) as img:
                # 计算正方形裁剪区域
                width, height = img.size
                size = min(width, height)
                left = (width - size) // 2
                top = (height - size) // 2
                right = left + size
                bottom = top + size
                
                # 裁剪并保存
                crop_img = img.crop((left, top, right, bottom))
                crop_path = str(self.menu_dir / f"crop_{os.path.basename(image_path)}")
                crop_img.save(crop_path)
                return crop_path
        except Exception as e:
            logger.error(f"Image cropping failed: {e}")
            return None

    async def game_timeout(self, group_id: str):
        """游戏超时处理"""
        await asyncio.sleep(30)
        
        if group_id in self.games and self.games[group_id].is_active:
            game = self.games[group_id]
            game.is_active = False
            
            # 发送答案
            await self.context.send_messag

import os
import random
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from PIL import Image
import astrbot.api.message_components as Comp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.utils.session_waiter import session_waiter, SessionController

# 插件注册
@register(
    "astrbot_plugin_pjskct",
    "bunana417",
    "Project SEKAI 倍率计算插件",
    "1.0.0",
    "https://github.com/banana417/astrbot_plugin_pjskct"
)
class PJSKGuessGame(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.config = self.load_config()
        self.aliases = self.load_aliases()
        self.active_games = {}  # 跟踪活跃游戏: {session_id: game_data}
        
    def load_config(self) -> dict:
        """加载插件配置"""
        default_config = {
            "image_dir": "/www/dk_project/dk_app/astrbot/astrbot_nrnR/data/guess_images",
            "crop_size": 150,
            "max_attempts": 5,
            "timeout": 60,
            "alias_file": "aliases.json"
        }
        
        # 尝试从用户配置加载，不存在则使用默认值
        try:
            config = {**default_config, **self.context.config}
            config["crop_size"] = int(config["crop_size"])
            config["max_attempts"] = int(config["max_attempts"])
            config["timeout"] = int(config["timeout"])
            return config
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return default_config
    
    def load_aliases(self) -> Dict[str, List[str]]:
        """加载角色别名映射"""
        alias_file = Path(__file__).parent / self.config["alias_file"]
        try:
            if alias_file.exists():
                with open(alias_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                # 创建默认别名文件
                default_aliases = {
                    "初音未来": ["初音", "miku", "Hatsune Miku", "ミク"],
                    "镜音铃": ["镜音", "铃", "rin", "リン"],
                    "镜音连": ["连", "len", "レン"],
                    "巡音流歌": ["巡音", "luka", "ルカ"],
                    "MEIKO": ["大姐", "メイコ"],
                    "KAITO": ["大哥", "カイト"],
                    "星乃一歌": ["一歌", "Hoshino Ichika"],
                    "天马咲希": ["咲希", "Tenma Saki"],
                    "望月穗波": ["穗波", "Mochizuki Honami"],
                    "日野森志步": ["志步", "Hinomori Shiho"],
                    "桃井爱莉": ["爱莉", "Momoi Airi"],
                    "小豆泽心羽": ["心羽", "Kohane"],
                    "天马司": ["司", "Tenma Tsukasa"],
                    "凤笑梦": ["笑梦", "Phoenix"],
                    "草薙宁宁": ["宁宁", "Kusanagi Nene"],
                    "神代类": ["类", "Kamishiro Rui"],
                    "宵崎奏": ["奏", "Yoisaki Kanade"],
                    "朝比奈真冬": ["真冬", "Asahina Mafuyu"],
                    "东云绘名": ["绘名", "Shinonome Ena"],
                    "晓山瑞希": ["瑞希", "Hiiragi Mizuki"]
                }
                with open(alias_file, "w", encoding="utf-8") as f:
                    json.dump(default_aliases, f, ensure_ascii=False, indent=2)
                return default_aliases
        except Exception as e:
            logger.error(f"加载别名文件失败: {e}")
            return {}
    
    def get_character_images(self) -> List[Tuple[str, str]]:
        """获取所有角色图片"""
        image_dir = Path(self.config["image_dir"])
        if not image_dir.is_dir():
            logger.error(f"图片目录不存在: {image_dir}")
            return []
        
        images = []
        for file in image_dir.glob("*.jpg"):
            parts = file.stem.split("_")
            if len(parts) >= 1:
                character = parts[0]
                images.append((character, str(file)))
        return images
    
    def get_random_image(self) -> Tuple[Optional[str], Optional[str], Optional[Image.Image]]:
        """随机选择一张图片"""
        images = self.get_character_images()
        if not images:
            logger.error("没有找到图片")
            return None, None, None
            
        character, image_path = random.choice(images)
        try:
            img = Image.open(image_path)
            return character, image_path, img
        except Exception as e:
            logger.error(f"加载图片失败: {e}")
            return None, None, None
    
    def crop_random_region(self, img: Image.Image) -> Image.Image:
        """随机裁剪图片区域"""
        width, height = img.size
        crop_size = self.config["crop_size"]
        
        # 确保裁剪尺寸有效
        crop_size = min(crop_size, width, height)
        
        # 随机选择裁剪位置
        left = random.randint(0, width - crop_size)
        top = random.randint(0, height - crop_size)
        
        return img.crop((left, top, left + crop_size, top + crop_size))
    
    def save_cropped_image(self, cropped_img: Image.Image) -> str:
        """保存裁剪后的图片并返回路径"""
        output_dir = Path(self.config["image_dir"]) / "cropped"
        output_dir.mkdir(exist_ok=True)
        
        output_path = output_dir / f"cropped_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg"
        cropped_img.save(output_path)
        return str(output_path)
    
    def is_correct_answer(self, guess: str, character: str) -> bool:
        """检查答案是否正确（支持别名）"""
        # 标准化输入
        normalized_guess = guess.strip().lower()
        
        # 检查直接匹配
        if normalized_guess == character.lower():
            return True
            
        # 检查别名匹配
        aliases = self.aliases.get(character, [])
        for alias in aliases:
            if normalized_guess == alias.lower():
                return True
                
        return False
    
    @filter.command("猜图")
    async def start_game(self, event: AstrMessageEvent):
        """开始猜图游戏"""
        session_id = event.unified_msg_origin
        
        # 检查是否已有活跃游戏
        if session_id in self.active_games:
            yield event.plain_result("你已经在进行一局游戏了！")
            return
            
        # 获取随机图片
        character, image_path, img = self.get_random_image()
        if not img:
            yield event.plain_result("获取图片失败，请稍后再试")
            return
            
        # 随机裁剪并保存
        cropped_img = self.crop_random_region(img)
        cropped_path = self.save_cropped_image(cropped_img)
        
        # 保存游戏状态
        self.active_games[session_id] = {
            "character": character,
            "attempts": 0,
            "max_attempts": self.config["max_attempts"],
            "start_time": datetime.now(),
            "image_path": image_path,
            "cropped_path": cropped_path
        }
        
        # 发送裁剪后的图片
        yield event.image_result(cropped_path)
        yield event.plain_result(f"猜猜这是哪位角色？发送 /猜+角色名 来回答，例如：/猜 初音未来")
        
        # 启动游戏会话
        try:
            await self.game_session(event)
        finally:
            # 游戏结束清理
            if session_id in self.active_games:
                game = self.active_games[session_id]
                # 删除裁剪图片
                if game.get("cropped_path") and os.path.exists(game["cropped_path"]):
                    try:
                        os.remove(game["cropped_path"])
                        logger.info(f"已删除裁剪图片: {game['cropped_path']}")
                    except Exception as e:
                        logger.error(f"删除裁剪图片失败: {e}")
                # 移除游戏状态
                del self.active_games[session_id]
    
    @filter.command("猜")
    async def process_guess(self, event: AstrMessageEvent, guess: str):
        """处理用户猜测"""
        session_id = event.unified_msg_origin
        
        # 检查是否在游戏中
        if session_id not in self.active_games:
            yield event.plain_result("当前没有进行中的游戏，请先发送 /猜图 开始游戏")
            return
            
        game = self.active_games[session_id]
        game["attempts"] += 1
        
        # 检查答案是否正确
        if self.is_correct_answer(guess, game["character"]):
            # 发送完整图片
            yield event.image_result(game["image_path"])
            yield event.plain_result(f"恭喜你猜对了！正确答案是: {game['character']}")
            event.stop_event()  # 结束游戏
            return
            
        # 检查尝试次数
        if game["attempts"] >= game["max_attempts"]:
            # 发送完整图片
            yield event.image_result(game["image_path"])
            yield event.plain_result(f"游戏结束，正确答案是: {game['character']}")
            event.stop_event()  # 结束游戏
            return
            
        # 猜错只告知用户猜错，不提供其他信息
        yield event.plain_result("不对哦")
    
    async def game_session(self, event: AstrMessageEvent):
        """游戏会话控制器"""
        session_id = event.unified_msg_origin
        
        @session_waiter(timeout=self.config["timeout"])
        async def game_waiter(controller: SessionController, event: AstrMessageEvent):
            # 检查超时
            game = self.active_games.get(session_id)
            if not game:
                controller.stop()
                return
                
            elapsed = (datetime.now() - game["start_time"]).seconds
            if elapsed >= self.config["timeout"]:
                # 发送完整图片
                yield event.image_result(game["image_path"])
                yield event.plain_result("时间到，游戏结束！")
                controller.stop()
        
        try:
            await game_waiter(event)
        except TimeoutError:
            # 超时异常处理
            if session_id in self.active_games:
                game = self.active_games[session_id]
                # 发送完整图片
                yield event.image_result(game["image_path"])
                yield event.plain_result("时间到，游戏结束！")
        except Exception as e:
            logger.error(f"游戏会话错误: {e}")
    
    async def terminate(self):
        """插件卸载时清理资源"""
        # 清理所有临时裁剪图片
        output_dir = Path(self.config["image_dir"]) / "cropped"
        if output_dir.exists():
            for file in output_dir.glob("*.jpg"):
                try:
                    os.remove(file)
                    logger.info(f"已删除临时图片: {file}")
                except Exception as e:
                    logger.error(f"删除临时图片失败: {e}")
        
        logger.info("PJSK猜图插件已卸载")
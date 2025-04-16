from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple, TypeVar, Generic, Iterable
from enum import Enum, auto
from functools import lru_cache
import itertools
import logging
from abc import ABC, abstractmethod
import json

# 初始化日志
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ====================== 核心数据模型（与具体科目解耦） ======================
class WeekDay(Enum):
    MONDAY = auto()
    TUESDAY = auto()
    WEDNESDAY = auto()
    THURSDAY = auto()
    FRIDAY = auto()
    SATURDAY = auto()
    SUNDAY = auto()

class DayPart(Enum):
    MORNING = auto()
    AFTERNOON = auto()
    EVENING = auto()

@dataclass
class TimeSlot:
    weekday: WeekDay
    day_part: DayPart
    period: int
    start_time: str
    end_time: str

@dataclass
class Subject:
    name: str
    category: str  # 用户自定义分类
    priority: int = 1  # 1-5优先级

@dataclass
class Teacher:
    name: str
    available_subjects: List[str]  # 能教的科目名称列表

@dataclass
class Classroom:
    name: str
    capacity: int
    is_special: bool = False  # 是否特殊教室

@dataclass
class StudentClass:
    name: str
    size: int

@dataclass
class ScheduleEntry:
    subject: Subject
    teacher: Teacher
    classroom: Classroom
    student_class: StudentClass
    time_slot: TimeSlot

@dataclass
class Schedule:
    entries: List[ScheduleEntry] = field(default_factory=list)

# ====================== 规则引擎系统 ======================
class RuleType(Enum):
    SUBJECT = auto()
    TEACHER = auto()
    CLASSROOM = auto()
    GENERAL = auto()

class RulePriority(Enum):
    MANDATORY = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4

@dataclass
class RuleResult:
    passed: bool
    message: str = ""

class Rule(ABC):
    def __init__(self, name: str, rule_type: RuleType, priority: RulePriority):
        self.name = name
        self.type = rule_type
        self.priority = priority
        self.enabled = True

    @abstractmethod
    def check(self, schedule: Schedule, entry: ScheduleEntry) -> RuleResult:
        pass

class SubjectConsecutiveRule(Rule):
    """科目连堂限制规则"""
    def __init__(self, max_consecutive: int = 2):
        super().__init__(
            "科目连堂限制",
            RuleType.SUBJECT,
            RulePriority.HIGH
        )
        self.max_consecutive = max_consecutive

    def check(self, schedule: Schedule, entry: ScheduleEntry) -> RuleResult:
        same_subject_entries = [
            e for e in schedule.entries
            if e.subject.name == entry.subject.name
               and e.time_slot.weekday == entry.time_slot.weekday
        ]

        consecutive_count = 1
        for e in same_subject_entries:
            if abs(e.time_slot.period - entry.time_slot.period) == 1:
                consecutive_count += 1

        if consecutive_count > self.max_consecutive:
            return RuleResult(
                False,
                f"科目 '{entry.subject.name}' 在同一天连续排课超过 {self.max_consecutive} 节"
            )
        return RuleResult(True)

class TeacherAvailabilityRule(Rule):
    """教师时间冲突检查"""
    def __init__(self):
        super().__init__(
            name="教师可用性检查",
            rule_type=RuleType.TEACHER,
            priority=RulePriority.MANDATORY
        )

    def check(self, schedule: Schedule, entry: ScheduleEntry) -> RuleResult:
        conflicting_entries = [
            e for e in schedule.entries
            if e.teacher.name == entry.teacher.name
               and e.time_slot.weekday == entry.time_slot.weekday
               and e.time_slot.period == entry.time_slot.period
        ]

        if conflicting_entries:
            return RuleResult(
                False,
                f"教师 '{entry.teacher.name}' 在该时段已有其他课程"
            )
        return RuleResult(True)

class ClassroomCapacityRule(Rule):
    """教室容量检查"""
    def __init__(self):
        super().__init__(
            name="教室容量检查",
            rule_type=RuleType.CLASSROOM,
            priority=RulePriority.MANDATORY
        )

    def check(self, schedule: Schedule, entry: ScheduleEntry) -> RuleResult:
        if entry.classroom.capacity < entry.student_class.size:
            return RuleResult(
                False,
                f"教室 '{entry.classroom.name}' 容量不足"
            )
        return RuleResult(True)

# ====================== 交互式排课系统 ======================
class Scheduler:
    def __init__(self):
        self.rules: List[Rule] = [
            SubjectConsecutiveRule(),
            TeacherAvailabilityRule(),
            ClassroomCapacityRule()
        ]
        self.schedule = Schedule()

    def add_custom_rule(self, rule: Rule):
        """允许用户添加自定义规则"""
        self.rules.append(rule)
        logger.info(f"已添加自定义规则: {rule.name}")

    def validate_entry(self, entry: ScheduleEntry) -> Tuple[bool, List[str]]:
        """验证单个课程条目"""
        errors = []
        for rule in sorted(self.rules, key=lambda r: r.priority.value):
            if not rule.enabled:
                continue

            result = rule.check(self.schedule, entry)
            if not result.passed:
                errors.append(f"[{rule.name}] {result.message}")
                if rule.priority == RulePriority.MANDATORY:
                    return False, errors
        return len(errors) == 0, errors

    def add_entry(self, entry: ScheduleEntry) -> bool:
        """添加课程条目到课表"""
        is_valid, errors = self.validate_entry(entry)
        if is_valid:
            self.schedule.entries.append(entry)
            logger.info(f"成功添加课程: {entry.subject.name} 在 {entry.time_slot.weekday.name} 第{entry.time_slot.period}节")
            return True
        else:
            logger.warning(f"添加课程失败: {', '.join(errors)}")
            return False

    def generate_schedule(self, input_data: Dict) -> Dict:
        """
        根据用户输入生成课表
        :param input_data: 包含科目、教师、教室等信息的字典
        :return: 排课结果和错误信息
        """
        result = {"success": False, "schedule": [], "errors": []}

        try:
            # 1. 解析用户输入
            subjects = self._parse_subjects(input_data.get("subjects", []))
            teachers = self._parse_teachers(input_data.get("teachers", []))
            classrooms = self._parse_classrooms(input_data.get("classrooms", []))
            classes = self._parse_classes(input_data.get("classes", []))

            # 2. 应用用户自定义规则
            for rule_config in input_data.get("rules", []):
                self._apply_custom_rule(rule_config)

            # 3. 尝试排课逻辑（示例简化版）
            for entry_config in input_data.get("schedule_attempts", []):
                entry = self._create_schedule_entry(
                    entry_config, subjects, teachers, classrooms, classes
                )
                if entry:
                    success = self.add_entry(entry)
                    if success:
                        result["schedule"].append({
                            "subject": entry.subject.name,
                            "teacher": entry.teacher.name,
                            "classroom": entry.classroom.name,
                            "class": entry.student_class.name,
                            "time": f"{entry.time_slot.weekday.name} {entry.time_slot.period}"
                        })
                    else:
                        result["errors"].append(f"排课失败: {entry_config}")

            result["success"] = len(result["errors"]) == 0
            return result

        except Exception as e:
            logger.error(f"排课过程中发生错误: {str(e)}")
            result["errors"].append(f"系统错误: {str(e)}")
            return result

    # ========== 输入解析方法 ==========
    def _parse_subjects(self, subject_data: List[Dict]) -> Dict[str, Subject]:
        return {
            s["name"]: Subject(
                name=s["name"],
                category=s.get("category", "default"),
                priority=s.get("priority", 3)
            )
            for s in subject_data
        }

    def _parse_teachers(self, teacher_data: List[Dict]) -> Dict[str, Teacher]:
        return {
            t["name"]: Teacher(
                name=t["name"],
                available_subjects=t.get("subjects", [])
            )
            for t in teacher_data
        }

    def _parse_classrooms(self, room_data: List[Dict]) -> Dict[str, Classroom]:
        return {
            r["name"]: Classroom(
                name=r["name"],
                capacity=r["capacity"],
                is_special=r.get("special", False)
            )
            for r in room_data
        }

    def _parse_classes(self, class_data: List[Dict]) -> Dict[str, StudentClass]:
        return {
            c["name"]: StudentClass(
                name=c["name"],
                size=c["size"]
            )
            for c in class_data
        }

    def _apply_custom_rule(self, rule_config: Dict):
        """应用用户自定义规则"""
        rule_type = rule_config.get("type")
        if rule_type == "no_consecutive":
            self.rules.append(SubjectConsecutiveRule(
                max_consecutive=rule_config.get("max", 1)
            ))
        # 可以扩展其他规则类型...

    def _create_schedule_entry(self, config: Dict,
                               subjects: Dict[str, Subject],
                               teachers: Dict[str, Teacher],
                               classrooms: Dict[str, Classroom],
                               classes: Dict[str, StudentClass]) -> Optional[ScheduleEntry]:
        """创建排课条目"""
        try:
            return ScheduleEntry(
                subject=subjects[config["subject"]],
                teacher=teachers[config["teacher"]],
                classroom=classrooms[config["classroom"]],
                student_class=classes[config["class"]],
                time_slot=TimeSlot(
                    weekday=WeekDay[config["weekday"].upper()],
                    day_part=DayPart[config["day_part"].upper()],
                    period=config["period"],
                    start_time=config.get("start_time", "08:00"),
                    end_time=config.get("end_time", "08:45")
                )
            )
        except KeyError as e:
            logger.warning(f"无效的排课配置: 缺少关键字段 {str(e)}")
            return None

# ====================== 交互接口 ======================
class InteractiveScheduler:
    def __init__(self):
        self.scheduler = Scheduler()

    def start_interactive_mode(self):
        """启动交互式排课模式"""
        print("=== 智能排课系统 ===")
        print("1. 添加科目\n2. 添加教师\n3. 添加教室\n4. 添加班级\n5. 尝试排课\n6. 显示当前课表\n7. 退出")

        while True:
            choice = input("请选择操作: ").strip()

            if choice == "1":
                self._add_subject()
            elif choice == "2":
                self._add_teacher()
            elif choice == "3":
                self._add_classroom()
            elif choice == "4":
                self._add_class()
            elif choice == "5":
                self._schedule_entry()
            elif choice == "6":
                self._show_schedule()
            elif choice == "7":
                break
            else:
                print("无效选择，请重新输入")

    def _add_subject(self):
        """交互式添加科目"""
        name = input("科目名称: ").strip()
        category = input("科目类别(如主科/理科/文科等): ").strip()
        priority = input("优先级(1-5, 默认为3): ").strip() or "3"

        # 在实际系统中这里会调用scheduler的相应方法
        print(f"已记录科目: {name} ({category}), 优先级{priority}")

    # 其他交互方法类似实现...

    def _schedule_entry(self):
        """交互式排课"""
        print("请提供排课信息:")
        subject = input("科目名称: ").strip()
        teacher = input("教师姓名: ").strip()
        classroom = input("教室名称: ").strip()
        class_name = input("班级名称: ").strip()
        weekday = input("星期几(如Monday): ").strip()
        period = input("第几节课(1-8): ").strip()

        # 构建输入数据
        input_data = {
            "schedule_attempts": [{
                "subject": subject,
                "teacher": teacher,
                "classroom": classroom,
                "class": class_name,
                "weekday": weekday,
                "period": int(period),
                "day_part": "MORNING" if int(period) <= 4 else "AFTERNOON"
            }]
        }

        # 调用排课引擎
        result = self.scheduler.generate_schedule(input_data)

        if result["success"]:
            print("排课成功!")
            print(json.dumps(result["schedule"], indent=2))
        else:
            print("排课失败，错误信息:")
            for error in result["errors"]:
                print(f"- {error}")

    def _show_schedule(self):
        """显示当前课表"""
        if not self.scheduler.schedule.entries:
            print("当前没有排课记录")
            return

        print("\n当前课表:")
        for entry in self.scheduler.schedule.entries:
            print(
                f"{entry.time_slot.weekday.name} 第{entry.time_slot.period}节: "
                f"{entry.subject.name} - {entry.teacher.name} "
                f"在 {entry.classroom.name} (班级: {entry.student_class.name})"
            )
        print()

class RuleManager:
    """规则管理器，用于管理和执行所有规则"""
    def __init__(self):
        self.rules: Dict[RuleType, List[Rule]] = {
            rule_type: [] for rule_type in RuleType
        }
        self._rule_cache = {}

    def add_rule(self, rule: Rule) -> None:
        """添加规则"""
        self.rules[rule.type].append(rule)
        self._clear_cache()
        logger.info(f"添加规则: {rule.name}")

    def remove_rule(self, rule: Rule) -> None:
        """移除规则"""
        if rule in self.rules[rule.type]:
            self.rules[rule.type].remove(rule)
            self._clear_cache()
            logger.info(f"移除规则: {rule.name}")

    def check_all_rules(self, schedule: Schedule, entry: ScheduleEntry) -> Tuple[bool, List[str]]:
        """检查所有规则"""
        cache_key = self._get_cache_key(schedule, entry)
        if cache_key in self._rule_cache:
            return self._rule_cache[cache_key]

        errors = []
        for rule_type in RuleType:
            for rule in sorted(self.rules[rule_type],
                               key=lambda r: r.priority.value):
                if not rule.enabled:
                    continue

                result = rule.check(schedule, entry)
                if not result.passed:
                    errors.append(f"[{rule.name}] {result.message}")
                    if rule.priority == RulePriority.MANDATORY:
                        self._rule_cache[cache_key] = (False, errors)
                        return False, errors

        result = (len(errors) == 0, errors)
        self._rule_cache[cache_key] = result
        return result

    def get_active_rules(self, rule_type: Optional[RuleType] = None) -> List[Rule]:
        """获取活动的规则"""
        if rule_type:
            return [rule for rule in self.rules[rule_type] if rule.enabled]
        return [rule for rules in self.rules.values()
                for rule in rules if rule.enabled]

    def _clear_cache(self) -> None:
        """清除规则检查缓存"""
        self._rule_cache.clear()

    def _get_cache_key(self, schedule: Schedule, entry: ScheduleEntry) -> str:
        """生成缓存键"""
        return f"{id(schedule)}_{id(entry)}"

    def create_default_rules(self) -> None:
        """创建默认规则集"""
        # 添加基本规则
        self.add_rule(SubjectConsecutiveRule())
        self.add_rule(TeacherAvailabilityRule())
        self.add_rule(ClassroomCapacityRule())

        # 可以添加更多默认规则...
        logger.info("已创建默认规则集")

    def to_dict(self) -> Dict:
        """将规则配置转换为字典格式"""
        return {
            rule_type.name: [
                {
                    "name": rule.name,
                    "priority": rule.priority.name,
                    "enabled": rule.enabled
                }
                for rule in rules
            ]
            for rule_type, rules in self.rules.items()
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'RuleManager':
        """从字典格式创建规则管理器"""
        manager = cls()
        for rule_type_name, rules_data in data.items():
            rule_type = RuleType[rule_type_name]
            for rule_data in rules_data:
                # 这里需要根据规则名称创建具体的规则实例
                # 可以维护一个规则名称到规则类的映射
                pass
        return manager


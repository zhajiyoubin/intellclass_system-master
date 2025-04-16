from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from enum import Enum
from datetime import time, timedelta
import json
from dataclasses_json import dataclass_json  # 需要安装 dataclasses-json 包

class Priority(Enum):
    DISABLED = "disabled"
    HIGH = "high"
    LOW = "low"
    NORMAL = "normal"

class DayPart(Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"

class WeekDay(Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

@dataclass_json
@dataclass
class TimeSlot:
    weekday: WeekDay  # 添加星期信息
    start_time: time
    end_time: time
    period_number: int
    day_part: DayPart

    def overlaps_with(self, other: 'TimeSlot') -> bool:
        """检查两个时间段是否重叠"""
        if self.weekday != other.weekday:
            return False
        return (self.start_time <= other.end_time and
                self.end_time >= other.start_time)

    def is_consecutive_with(self, other: 'TimeSlot') -> bool:
        """检查是否与另一时间段连续"""
        if self.weekday != other.weekday:
            return False
        return abs(self.period_number - other.period_number) == 1

@dataclass_json
@dataclass
class Teacher:
    id: str  # 教师ID
    name: str  # 教师姓名
    subjects: List[str]  # 可教授的科目
    max_hours_per_day: int = 6  # 每天最大课时数
    available_times: List[TimeSlot] = field(default_factory=list)  # 可用时间段
    preferred_subjects: Dict[str, Priority] = field(default_factory=dict)  # 偏好科目

    def can_teach_subject(self, subject: str) -> bool:
        """检查是否可以教授某个科目"""
        return subject in self.subjects

    def is_available_at(self, time_slot: TimeSlot) -> bool:
        """检查某个时间段是否可用"""
        if not self.available_times:  # 如果没有指定可用时间，则默认都可用
            return True
        return any(at.overlaps_with(time_slot) for at in self.available_times)

    def get_daily_workload(self, schedule: 'Schedule', weekday: WeekDay) -> int:
        """获取某一天的工作量"""
        return sum(1 for entry in schedule.get_teacher_schedule(self)
                   if entry.time_slot.weekday == weekday)

@dataclass
class Subject:
    name: str
    category: str  # 添加 category 字段
    weekly_hours: int
    priority: int = 1  # 设置默认优先级
    requires_consecutive_periods: bool = False  # 是否需要连堂
    max_periods_per_day: int = 2  # 每天最大课时数
    allowed_day_parts: List[DayPart] = field(
        default_factory=lambda: [DayPart.MORNING, DayPart.AFTERNOON]
    )
    conflicting_subjects: Set[str] = field(default_factory=set)
    required_room_types: Set[str] = field(default_factory=set)

    def can_be_scheduled_at(self, time_slot: TimeSlot) -> bool:
        """检查是否可以在指定时间段安排"""
        return time_slot.day_part in self.allowed_day_parts  # 简化检查条件

    def conflicts_with(self, other: 'Subject') -> bool:
        """检查是否与其他科目冲突"""
        return (other.name in self.conflicting_subjects or
                self.name in other.conflicting_subjects)

@dataclass_json
@dataclass
class Classroom:
    id: str
    name: str
    floor: int
    location: str
    room_type: str
    capacity: int
    is_special: bool = False  # 添加这个字段，默认为 False
    equipment: Set[str] = field(default_factory=set)
    available_times: List[TimeSlot] = field(default_factory=list)

    def is_suitable_for(self, subject: Subject) -> bool:
        """检查是否适合某个科目"""
        if not subject.required_room_types:  # 如果科目没有特殊要求，任何教室都可以
            return True
        return self.room_type in subject.required_room_types

    def is_available_at(self, time_slot: TimeSlot) -> bool:
        """检查某个时间段是否可用"""
        if not self.available_times:  # 如果没有指定可用时间，则默认都可用
            return True
        return any(at.overlaps_with(time_slot) for at in self.available_times)

@dataclass_json
@dataclass
class Class:
    grade: str
    name: str
    student_count: int
    subjects: List[Subject] = field(default_factory=list)
    head_teacher: Optional[Teacher] = None
    special_requirements: Set[str] = field(default_factory=set)

    def get_weekly_hours(self) -> Dict[str, int]:
        """获取每周课时统计"""
        return {subject.name: subject.weekly_hours for subject in self.subjects}

@dataclass
class TimeTable:
    """课程时间表配置"""
    class_duration: int  # 每节课时长（分钟）
    break_duration: int  # 课间休息时长（分钟）
    morning_start: time  # 上午开始时间
    afternoon_start: time  # 下午开始时间
    evening_start: Optional[time] = None  # 晚上开始时间（可选）
    periods_per_morning: int = 4  # 上午课时数
    periods_per_afternoon: int = 4  # 下午课时数
    periods_per_evening: int = 0  # 晚上课时数（默认为0）

    def get_period_time(self, period: int) -> Tuple[str, str]:
        """获取指定课节的开始和结束时间"""
        total_duration = self.class_duration + self.break_duration

        # 确定基准时间
        if period <= self.periods_per_morning:
            base_time = self.morning_start
        elif period <= self.periods_per_morning + self.periods_per_afternoon:
            base_time = self.afternoon_start
            period -= self.periods_per_morning
        else:
            if not self.evening_start:
                raise ValueError("Evening schedule not available")
            base_time = self.evening_start
            period -= (self.periods_per_morning + self.periods_per_afternoon)

        # 计算开始时间
        minutes_from_base = (period - 1) * total_duration
        start_hour = base_time.hour + minutes_from_base // 60
        start_minute = base_time.minute + minutes_from_base % 60

        if start_minute >= 60:
            start_hour += 1
            start_minute -= 60

        start_time = f"{start_hour:02d}:{start_minute:02d}"

        # 计算结束时间
        end_minutes = minutes_from_base + self.class_duration
        end_hour = base_time.hour + end_minutes // 60
        end_minute = base_time.minute + end_minutes % 60

        if end_minute >= 60:
            end_hour += 1
            end_minute -= 60

        end_time = f"{end_hour:02d}:{end_minute:02d}"

        return start_time, end_time

    def get_all_periods(self) -> List[Tuple[int, str, str]]:
        """获取所有课节的时间安排"""
        periods = []
        total_periods = (self.periods_per_morning +
                         self.periods_per_afternoon +
                         self.periods_per_evening)

        for period in range(1, total_periods + 1):
            start_time, end_time = self.get_period_time(period)
            periods.append((period, start_time, end_time))

        return periods

    def is_valid_period(self, period: int) -> bool:
        """检查课节编号是否有效"""
        return 1 <= period <= (self.periods_per_morning +
                               self.periods_per_afternoon +
                               self.periods_per_evening)

    def get_day_part(self, period: int) -> DayPart:
        """获取课节所属的时间段（上午/下午/晚上）"""
        if not self.is_valid_period(period):
            raise ValueError(f"Invalid period number: {period}")

        if period <= self.periods_per_morning:
            return DayPart.MORNING
        elif period <= self.periods_per_morning + self.periods_per_afternoon:
            return DayPart.AFTERNOON
        return DayPart.EVENING

@dataclass_json
@dataclass
class ScheduleConfig:
    name: str
    weekdays: List[WeekDay]
    timetable: TimeTable
    allow_split_class: bool = False
    allow_mixed_grade: bool = False
    max_consecutive_same_subject: int = 2
    min_subject_interval: int = 1

    def validate(self) -> List[str]:
        """验证配置是否合法"""
        errors = []
        if not self.weekdays:
            errors.append("必须指定上课日")
        if self.timetable.periods_per_morning + self.timetable.periods_per_afternoon == 0:
            errors.append("必须至少安排一节课")
        return errors

@dataclass_json
@dataclass
class ScheduleEntry:
    class_info: Class
    subject: Subject
    teacher: Teacher
    classroom: Classroom
    time_slot: TimeSlot
    is_fixed: bool = False

    def validate(self, schedule: 'Schedule') -> List[str]:
        """验证课程安排是否合法"""
        errors = []

        # 检查教师可用性
        if not self.teacher.is_available_at(self.time_slot):
            errors.append(f"教师 {self.teacher.name} 在该时段不可用")

        # 检查教室可用性
        if not self.classroom.is_suitable_for(self.subject):
            errors.append(f"教室 {self.classroom.name} 不适合该科目")

        # 检查科目时间限制
        if not self.subject.can_be_scheduled_at(self.time_slot):
            errors.append(f"科目 {self.subject.name} 不能在该时段安排")

        return errors

@dataclass
class Schedule:
    config: ScheduleConfig
    entries: List[ScheduleEntry] = field(default_factory=list)

    def add_entry(self, entry: ScheduleEntry) -> bool:
        """添加课程条目"""
        if self.has_conflicts(entry):
            return False
        self.entries.append(entry)
        return True

    def has_conflicts(self, new_entry: ScheduleEntry) -> bool:
        """检查是否存在冲突"""
        for entry in self.entries:
            # 检查时间冲突
            if entry.time_slot.weekday == new_entry.time_slot.weekday and \
                    entry.time_slot.period_number == new_entry.time_slot.period_number:
                # 同一时间段的冲突检查
                if (entry.class_info == new_entry.class_info or  # 同一班级
                        entry.teacher == new_entry.teacher or        # 同一教师
                        entry.classroom == new_entry.classroom):     # 同一教室
                    return True
        return False

    def remove_entry(self, entry: ScheduleEntry):
        """删除课程安排"""
        self.entries.remove(entry)

    def get_class_schedule(self, class_info: Class) -> List[ScheduleEntry]:
        """获取班级课表"""
        return [entry for entry in self.entries if entry.class_info == class_info]

    def get_teacher_schedule(self, teacher: Teacher) -> List[ScheduleEntry]:
        """获取教师课表"""
        return [entry for entry in self.entries if entry.teacher == teacher]

    def get_classroom_schedule(self, classroom: Classroom) -> List[ScheduleEntry]:
        """获取教室课表"""
        return [entry for entry in self.entries if entry.classroom == classroom]

    def get_entries_by_day(self, weekday: WeekDay) -> List[ScheduleEntry]:
        """获取某天的所有课程"""
        return [e for e in self.entries if e.time_slot.weekday == weekday]

    def export_to_json(self, file_path: str):
        """导出课表为JSON格式"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def import_from_json(cls, file_path: str) -> 'Schedule':
        """从JSON文件导入课表"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)
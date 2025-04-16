from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from datetime import time
import random
from models import (
    TimeSlot, Subject, Teacher, Classroom, Class, Schedule,
    ScheduleEntry, ScheduleConfig, WeekDay, DayPart, TimeTable
)
from rules import (Rule, RuleResult, RuleManager)
import logging

logger = logging.getLogger(__name__)


@dataclass
class SchedulingConstraints:
    """排课约束条件"""
    max_daily_hours: Dict[str, int] = field(default_factory=lambda: {"default": 8})
    preferred_time_slots: Dict[str, List[TimeSlot]] = field(default_factory=dict)
    subject_consecutive: Dict[str, bool] = field(default_factory=dict)
    special_room_requirements: Dict[str, Set[str]] = field(default_factory=dict)


class SmartScheduler:
    def __init__(self, config: ScheduleConfig, rule_manager: RuleManager):
        self.config = config
        self.rule_manager = rule_manager
        self.schedule = Schedule(config=config)
        self.constraints = SchedulingConstraints()

    def generate_schedule(self, classes: List[Class], teachers: List[Teacher],
                          classrooms: List[Classroom]) -> Tuple[Schedule, List[str]]:
        """生成完整的课表"""
        errors = []

        for class_ in classes:
            sorted_subjects = self._sort_subjects_by_priority(class_.subjects)
            for subject in sorted_subjects:
                remaining_hours = subject.weekly_hours
                while remaining_hours > 0:
                    entry = self._try_schedule_subject(class_, subject, teachers, classrooms)
                    if entry:
                        result = self.schedule.add_entry(entry)
                        if not result:
                            error_msg = f"无法为 {class_.name} 安排 {subject.name} 课程：规则冲突"
                            logger.error(error_msg)
                            errors.append(error_msg)
                            break
                        remaining_hours -= 1
                    else:
                        error_msg = self._get_scheduling_error_message(class_, subject, teachers, classrooms)
                        logger.error(error_msg)
                        errors.append(error_msg)
                        break

        return self.schedule, errors

    def _sort_subjects_by_priority(self, subjects):
        return sorted(subjects, key=lambda s: (s.priority, s.weekly_hours), reverse=True)

    def _get_scheduling_error_message(self, class_, subject, teachers, classrooms):
        available_teachers = [t for t in teachers if subject.name in t.subjects]
        if not available_teachers:
            return f"无法为 {class_.name} 安排 {subject.name} 课程：没有合适的教师"
        suitable_classrooms = [c for c in classrooms if c.is_suitable_for(subject)]
        if not suitable_classrooms:
            return f"无法为 {class_.name} 安排 {subject.name} 课程：没有合适的教室"
        return f"无法为 {class_.name} 安排 {subject.name} 课程：时间段冲突"

    def _try_schedule_subject(self, class_: Class, subject: Subject,
                              teachers: List[Teacher], classrooms: List[Classroom]) -> Optional[ScheduleEntry]:
        available_teachers = [t for t in teachers if subject.name in t.subjects]
        if not available_teachers:
            logger.debug(f"没有找到可教授 {subject.name} 的教师")
            return None

        suitable_classrooms = [c for c in classrooms if
                               (c.is_suitable_for(subject) and c.capacity >= class_.student_count)]
        if not suitable_classrooms:
            logger.debug(f"没有找到适合 {subject.name} 的教室")
            return None

        max_attempts = 3
        for attempt in range(max_attempts):
            weekdays = list(self.config.weekdays)
            random.shuffle(weekdays)
            periods = list(range(1, self._get_daily_periods()))
            random.shuffle(periods)

            for weekday in weekdays:
                for period in periods:
                    time_slot = self._create_time_slot(weekday, period)

                    if not subject.can_be_scheduled_at(time_slot):
                        logger.debug(f"{subject.name} 不能在 {weekday.name} 第{period}节安排")
                        continue

                    random.shuffle(available_teachers)
                    random.shuffle(suitable_classrooms)

                    for teacher in available_teachers:
                        if not teacher.is_available_at(time_slot):
                            logger.debug(f"教师 {teacher.name} 在该时段不可用")
                            continue

                        for classroom in suitable_classrooms:
                            if not classroom.is_available_at(time_slot):
                                logger.debug(f"教室 {classroom.name} 在该时段不可用")
                                continue

                            entry = ScheduleEntry(
                                class_info=class_,
                                subject=subject,
                                teacher=teacher,
                                classroom=classroom,
                                time_slot=time_slot
                            )

                            if not self.schedule.has_conflicts(entry):
                                return entry
                            else:
                                logger.debug(f"课程安排与现有课表冲突")

        return None

    def _create_time_slot(self, weekday: WeekDay, period: int) -> TimeSlot:
        start_time, end_time = self.config.timetable.get_period_time(period)
        day_part = self._get_day_part(period)
        return TimeSlot(
            weekday=weekday,
            start_time=start_time,
            end_time=end_time,
            period_number=period,
            day_part=day_part
        )

    def _get_day_part(self, period: int) -> DayPart:
        if period <= self.config.timetable.periods_per_morning:
            return DayPart.MORNING
        elif period <= (self.config.timetable.periods_per_morning +
                        self.config.timetable.periods_per_afternoon):
            return DayPart.AFTERNOON
        return DayPart.EVENING

    def _get_daily_periods(self) -> int:
        return (self.config.timetable.periods_per_morning +
                self.config.timetable.periods_per_afternoon +
                self.config.timetable.periods_per_evening)


class SchedulerService:
    """排课服务类，提供高层接口"""

    def __init__(self, config: ScheduleConfig, rule_manager: RuleManager):
        self.scheduler = SmartScheduler(config, rule_manager)

    def create_schedule(self, classes: List[Class], teachers: List[Teacher],
                        classrooms: List[Classroom]) -> Dict:
        try:
            schedule, errors = self.scheduler.generate_schedule(classes, teachers, classrooms)

            result = {
                "success": len(errors) == 0,
                "schedule": self._format_schedule(schedule),
                "errors": errors
            }

            if result["success"]:
                logger.info("课表生成成功")
            else:
                logger.warning(f"课表生成存在问题: {errors}")

            return result

        except Exception as e:
            logger.error(f"生成课表时发生错误: {str(e)}")
            return {
                "success": False,
                "schedule": [],
                "errors": [f"系统错误: {str(e)}"]
            }

    def _format_schedule(self, schedule: Schedule) -> List[Dict]:
        weekday_map = {
            'monday': '一',
            'tuesday': '二',
            'wednesday': '三',
            'thursday': '四',
            'friday': '五'
        }
        formatted = []
        for entry in schedule.entries:
            formatted.append({
                "class": entry.class_info.name,
                "subject": entry.subject.name,
                "teacher": entry.teacher.name,
                "classroom": entry.classroom.name,
                "weekday": weekday_map[entry.time_slot.weekday.value],
                "period": entry.time_slot.period_number,
                "time": f"{entry.time_slot.start_time}-{entry.time_slot.end_time}"
            })
        return formatted
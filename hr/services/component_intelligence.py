from django.db.models import Q, Count, Avg
from django.utils import timezone
from datetime import timedelta
from hr.models import SalaryComponent, Employee
from decimal import Decimal
import re


class ComponentIntelligence:
    """خدمة الذكاء الاصطناعي لتصنيف ومعالجة بنود الراتب"""
    
    def __init__(self):
        self.classification_rules = self._load_classification_rules()
        self.pattern_cache = {}
    
    def _load_classification_rules(self):
        """تحميل قواعد التصنيف الذكي"""
        return {
            'personal': {
                'keywords': ['قرض', 'مقدم', 'سلفة', 'دين', 'استقطاع شخصي'],
                'patterns': [r'قرض.*', r'مقدم.*', r'سلفة.*'],
                'amount_range': (100, 50000),  # نطاق المبالغ المتوقع
                'duration_months': (1, 60)     # مدة القرض المتوقعة
            },
            'temporary': {
                'keywords': ['مؤقت', 'بدل مؤقت', 'حافز مؤقت', 'علاوة مؤقتة'],
                'patterns': [r'.*مؤقت.*', r'بدل.*مؤقت', r'حافز.*شهر'],
                'has_end_date': True,
                'max_duration_months': 12
            },
            'exceptional': {
                'keywords': ['مكافأة', 'حافز', 'بونص', 'عمولة', 'تعويض'],
                'patterns': [r'مكافأة.*', r'حافز.*', r'بونص.*', r'عمولة.*'],
                'frequency': 'irregular',
                'amount_variance': 'high'
            },
            'adjustment': {
                'keywords': ['تعديل', 'تجريبي', 'اختبار', 'مراجعة'],
                'patterns': [r'تعديل.*', r'تجريبي.*', r'اختبار.*'],
                'temporary_nature': True,
                'requires_review': True
            }
        }
    
    def suggest_component_source(self, component):
        """اقتراح مصدر البند بناءً على التحليل الذكي"""
        
        # إذا كان البند من العقد، فهو من العقد
        if component.is_from_contract:
            return 'contract'
        
        # تحليل اسم البند
        name_analysis = self._analyze_component_name(component.name)
        
        # تحليل خصائص البند
        characteristics = self._analyze_component_characteristics(component)
        
        # تحليل الأنماط التاريخية
        historical_patterns = self._analyze_historical_patterns(component)
        
        # حساب النقاط لكل تصنيف
        scores = self._calculate_classification_scores(
            name_analysis, characteristics, historical_patterns
        )
        
        # إرجاع التصنيف الأعلى نقاطاً
        best_classification = max(scores.items(), key=lambda x: x[1])
        
        # إذا كانت النقاط منخفضة، ابق على التصنيف الحالي
        if best_classification[1] < 0.6:
            return component.source or 'contract'
        
        return best_classification[0]
    
    def _analyze_component_name(self, name):
        """تحليل اسم البند للتصنيف"""
        analysis = {}
        name_lower = name.lower()
        
        for source, rules in self.classification_rules.items():
            score = 0
            
            # فحص الكلمات المفتاحية
            for keyword in rules['keywords']:
                if keyword in name_lower:
                    score += 2
            
            # فحص الأنماط
            for pattern in rules.get('patterns', []):
                if re.search(pattern, name_lower):
                    score += 1.5
            
            analysis[source] = score
        
        return analysis
    
    def _analyze_component_characteristics(self, component):
        """تحليل خصائص البند"""
        analysis = {}
        
        for source, rules in self.classification_rules.items():
            score = Decimal('0')
            
            # فحص نطاق المبلغ
            if 'amount_range' in rules:
                min_amount, max_amount = rules['amount_range']
                if min_amount <= component.amount <= max_amount:
                    score += Decimal('1')
            
            # فحص وجود تاريخ انتهاء
            if rules.get('has_end_date'):
                if component.effective_to:
                    score += Decimal('2')
                else:
                    score -= Decimal('1')
            
            # فحص مدة البند
            if 'max_duration_months' in rules and component.effective_to:
                duration = self._calculate_duration_months(
                    component.effective_from or timezone.now().date(),
                    component.effective_to
                )
                if duration <= rules['max_duration_months']:
                    score += Decimal('1')
            
            # فحص الطبيعة المؤقتة
            if rules.get('temporary_nature'):
                if component.effective_to or not component.is_recurring:
                    score += Decimal('1.5')
            
            analysis[source] = score
        
        return analysis
    
    def _analyze_historical_patterns(self, component):
        """تحليل الأنماط التاريخية للبنود المشابهة"""
        analysis = {}
        
        # البحث عن بنود مشابهة
        similar_components = SalaryComponent.objects.filter(
            name__icontains=component.name[:10],  # أول 10 أحرف
            component_type=component.component_type
        ).exclude(id=component.id)
        
        if similar_components.exists():
            # تحليل التصنيفات الشائعة
            source_counts = similar_components.values('source').annotate(
                count=Count('source')
            ).order_by('-count')
            
            total_similar = similar_components.count()
            
            for source_data in source_counts:
                source = source_data['source']
                count = source_data['count']
                percentage = Decimal(count) / Decimal(total_similar)
                
                analysis[source] = percentage * Decimal('2')  # وزن الأنماط التاريخية
        
        return analysis
    
    def _calculate_classification_scores(self, name_analysis, characteristics, historical_patterns):
        """حساب النقاط النهائية لكل تصنيف"""
        scores = {}
        
        all_sources = set(name_analysis.keys()) | set(characteristics.keys()) | set(historical_patterns.keys())
        
        for source in all_sources:
            name_score = name_analysis.get(source, 0)
            char_score = characteristics.get(source, 0)
            hist_score = historical_patterns.get(source, 0)
            
            # حساب النقاط المرجحة
            total_score = (
                name_score * Decimal('0.4') +      # وزن اسم البند 40%
                char_score * Decimal('0.4') +      # وزن الخصائص 40%
                hist_score * Decimal('0.2')        # وزن الأنماط التاريخية 20%
            )
            
            # تطبيع النقاط (0-1)
            normalized_score = min(total_score / Decimal('10'), Decimal('1.0'))
            scores[source] = normalized_score
        
        return scores
    
    def _calculate_duration_months(self, start_date, end_date):
        """حساب المدة بالشهور"""
        if not start_date or not end_date:
            return 0
        
        months = (end_date.year - start_date.year) * 12
        months += end_date.month - start_date.month
        
        return max(months, 0)
    
    def analyze_component_patterns(self, employee):
        """تحليل أنماط بنود الموظف (باستثناء الراتب الأساسي)"""
        components = SalaryComponent.objects.filter(
            employee=employee,
            is_active=True,
            is_basic=False  # استبعاد الراتب الأساسي
        )
        
        patterns = {
            'total_components': components.count(),
            'by_source': {},
            'by_type': {},
            'financial_summary': {},
            'anomalies': [],
            'recommendations': []
        }
        
        # تحليل حسب المصدر
        for source, _ in SalaryComponent.COMPONENT_SOURCE_CHOICES:
            source_components = components.filter(source=source)
            patterns['by_source'][source] = {
                'count': source_components.count(),
                'total_amount': sum(comp.amount for comp in source_components),
                'components': list(source_components)
            }
        
        # تحليل حسب النوع
        for comp_type in ['earning', 'deduction']:
            type_components = components.filter(component_type=comp_type)
            patterns['by_type'][comp_type] = {
                'count': type_components.count(),
                'total_amount': sum(comp.amount for comp in type_components),
                'average_amount': type_components.aggregate(
                    avg=Avg('amount')
                )['avg'] or 0
            }
        
        # ملخص مالي
        total_earnings = patterns['by_type'].get('earning', {}).get('total_amount', 0)
        total_deductions = patterns['by_type'].get('deduction', {}).get('total_amount', 0)
        
        patterns['financial_summary'] = {
            'total_earnings': total_earnings,
            'total_deductions': total_deductions,
            'net_salary': total_earnings - total_deductions,
            'deduction_ratio': (total_deductions / total_earnings * Decimal('100')) if total_earnings > 0 else Decimal('0')
        }
        
        # اكتشاف الشذوذ
        patterns['anomalies'] = self._detect_anomalies(components)
        
        # توليد التوصيات
        patterns['recommendations'] = self._generate_pattern_recommendations(patterns)
        
        return patterns
    
    def _detect_anomalies(self, components):
        """اكتشاف الشذوذ في البنود"""
        anomalies = []
        
        # البنود المنتهية ولكن لا تزال نشطة
        expired_active = components.filter(
            effective_to__lt=timezone.now().date(),
            is_active=True
        )
        
        for component in expired_active:
            anomalies.append({
                'type': 'expired_but_active',
                'component': component,
                'message': f'البند "{component.name}" منتهي الصلاحية ولكن لا يزال نشطاً',
                'severity': 'medium'
            })
        
        # البنود بمبالغ غير عادية
        avg_amount = components.aggregate(avg=Avg('amount'))['avg'] or Decimal('0')
        if avg_amount > 0:
            unusual_amounts = components.filter(
                Q(amount__gt=avg_amount * Decimal('5')) | Q(amount__lt=avg_amount * Decimal('0.1'))
            )
            
            for component in unusual_amounts:
                anomalies.append({
                    'type': 'unusual_amount',
                    'component': component,
                    'message': f'البند "{component.name}" له مبلغ غير عادي: {component.amount}',
                    'severity': 'low'
                })
        
        # البنود المكررة
        duplicate_names = components.values('name').annotate(
            count=Count('name')
        ).filter(count__gt=1)
        
        for dup in duplicate_names:
            duplicate_components = components.filter(name=dup['name'])
            anomalies.append({
                'type': 'duplicate_names',
                'components': list(duplicate_components),
                'message': f'يوجد {dup["count"]} بند بنفس الاسم: "{dup["name"]}"',
                'severity': 'high'
            })
        
        return anomalies
    
    def _generate_pattern_recommendations(self, patterns):
        """توليد توصيات بناءً على تحليل الأنماط"""
        recommendations = []
        
        # توصيات للبنود الشخصية
        personal_count = patterns['by_source'].get('personal', {}).get('count', 0)
        if personal_count > 3:
            recommendations.append({
                'type': 'personal_components_review',
                'message': f'يوجد {personal_count} بند شخصي، يُنصح بمراجعتها دورياً',
                'priority': 'medium'
            })
        
        # توصيات للخصومات العالية
        deduction_ratio = patterns['financial_summary'].get('deduction_ratio', 0)
        if deduction_ratio > 30:
            recommendations.append({
                'type': 'high_deductions',
                'message': f'نسبة الخصومات عالية ({deduction_ratio:.1f}%)، يُنصح بالمراجعة',
                'priority': 'high'
            })
        
        # توصيات للبنود المؤقتة
        temporary_count = patterns['by_source'].get('temporary', {}).get('count', 0)
        if temporary_count > 0:
            recommendations.append({
                'type': 'temporary_components_review',
                'message': f'يوجد {temporary_count} بند مؤقت، تأكد من تواريخ الانتهاء',
                'priority': 'medium'
            })
        
        return recommendations
    
    def predict_component_renewal(self, component):
        """التنبؤ بحاجة البند للتجديد"""
        if not component.effective_to:
            return {'needs_renewal': False, 'reason': 'بند دائم'}
        
        days_until_expiry = (component.effective_to - timezone.now().date()).days
        
        # إذا كان البند سينتهي خلال 30 يوم
        if days_until_expiry <= 30:
            # تحليل التاريخ السابق للبند
            renewal_history = self._analyze_renewal_history(component)
            
            prediction = {
                'needs_renewal': True,
                'days_until_expiry': days_until_expiry,
                'renewal_probability': self._calculate_renewal_probability(component, renewal_history),
                'suggested_duration': self._suggest_renewal_duration(component, renewal_history),
                'history': renewal_history
            }
            
            return prediction
        
        return {'needs_renewal': False, 'days_until_expiry': days_until_expiry}
    
    def _analyze_renewal_history(self, component):
        """تحليل تاريخ تجديد البند"""
        # البحث عن بنود مشابهة سابقة
        similar_components = SalaryComponent.objects.filter(
            employee=component.employee,
            name=component.name,
            component_type=component.component_type
        ).exclude(id=component.id).order_by('-created_at')
        
        history = {
            'previous_renewals': similar_components.count(),
            'average_duration': 0,
            'renewal_pattern': 'irregular'
        }
        
        if similar_components.exists():
            # حساب متوسط مدة التجديد
            durations = []
            for comp in similar_components:
                if comp.effective_from and comp.effective_to:
                    duration = self._calculate_duration_months(
                        comp.effective_from, comp.effective_to
                    )
                    durations.append(duration)
            
            if durations:
                history['average_duration'] = sum(durations) / len(durations)
                
                # تحديد نمط التجديد
                if len(set(durations)) == 1:
                    history['renewal_pattern'] = 'regular'
                elif max(durations) - min(durations) <= 2:
                    history['renewal_pattern'] = 'semi_regular'
        
        return history
    
    def _calculate_renewal_probability(self, component, history):
        """حساب احتمالية التجديد"""
        base_probability = Decimal('0.5')
        
        # زيادة الاحتمالية بناءً على التاريخ
        if history['previous_renewals'] > 0:
            base_probability += min(history['previous_renewals'] * Decimal('0.1'), Decimal('0.3'))
        
        # زيادة الاحتمالية للبنود الشخصية
        if component.source == 'personal':
            base_probability += Decimal('0.2')
        
        # زيادة الاحتمالية للبنود المتكررة
        if component.is_recurring:
            base_probability += Decimal('0.1')
        
        # زيادة الاحتمالية للتجديد التلقائي
        if component.auto_renew:
            base_probability += Decimal('0.3')
        
        return min(base_probability, Decimal('1.0'))
    
    def _suggest_renewal_duration(self, component, history):
        """اقتراح مدة التجديد"""
        # إذا كان هناك تاريخ سابق، استخدم المتوسط
        if history['average_duration'] > 0:
            return int(history['average_duration'])
        
        # إذا كان هناك فترة تجديد محددة
        if component.renewal_period_months:
            return component.renewal_period_months
        
        # اقتراحات افتراضية حسب النوع
        default_durations = {
            'personal': 12,      # القروض عادة سنة
            'temporary': 6,      # البنود المؤقتة 6 شهور
            'exceptional': 3,    # البنود الاستثنائية 3 شهور
            'adjustment': 1      # التعديلات شهر واحد
        }
        
        return default_durations.get(component.source, 6)

/**
 * فلترة ذكية للمواقع حسب الفرع المختار
 * تُستخدم في نماذج الموظفين والمصاريف
 */

(function() {
  'use strict';

  // تهيئة عند تحميل الصفحة
  document.addEventListener('DOMContentLoaded', function() {
    const branchSelect = document.getElementById('branch_id');
    const siteSelect = document.getElementById('site_id');
    
    if (!branchSelect || !siteSelect) {
      return; // الحقول غير موجودة في هذه الصفحة
    }

    // حفظ كل المواقع الأصلية
    const allSitesOptions = Array.from(siteSelect.options).map(opt => ({
      value: opt.value,
      text: opt.text,
      branchId: opt.getAttribute('data-branch-id')
    }));

    /**
     * فلترة المواقع بناءً على الفرع المختار
     */
    function filterSitesByBranch() {
      const selectedBranchId = branchSelect.value;
      
      if (!selectedBranchId || selectedBranchId === '0' || selectedBranchId === '') {
        // إذا لم يُختر فرع، أظهر كل المواقع
        repopulateSites(allSitesOptions);
        siteSelect.disabled = true;
        return;
      }

      // فلترة المواقع التي تنتمي للفرع المختار
      const filtered = allSitesOptions.filter(opt => {
        return opt.value === '0' || opt.branchId === selectedBranchId;
      });

      repopulateSites(filtered);
      siteSelect.disabled = false;
    }

    /**
     * إعادة ملء قائمة المواقع
     */
    function repopulateSites(options) {
      const currentValue = siteSelect.value;
      siteSelect.innerHTML = '';
      
      options.forEach(opt => {
        const option = document.createElement('option');
        option.value = opt.value;
        option.text = opt.text;
        if (opt.branchId) {
          option.setAttribute('data-branch-id', opt.branchId);
        }
        siteSelect.appendChild(option);
      });

      // استعادة القيمة المختارة إن كانت ضمن القائمة المفلترة
      if (options.some(o => o.value === currentValue)) {
        siteSelect.value = currentValue;
      } else {
        siteSelect.value = '0'; // إعادة تعيين للخيار الافتراضي
      }
    }

    /**
     * جلب المواقع من API بناءً على الفرع (للتحميل الديناميكي)
     */
    async function loadSitesFromAPI(branchId) {
      if (!branchId || branchId === '0') {
        siteSelect.innerHTML = '<option value="0">-- بدون موقع --</option>';
        siteSelect.disabled = true;
        return;
      }

      try {
        const response = await fetch(`/branches/api/sites/${branchId}`);
        if (!response.ok) throw new Error('فشل تحميل المواقع');
        
        const data = await response.json();
        const sites = data.results || [];

        siteSelect.innerHTML = '<option value="0">-- بدون موقع --</option>';
        sites.forEach(site => {
          const option = document.createElement('option');
          option.value = site.id;
          option.text = site.text || site.name;
          option.setAttribute('data-branch-id', branchId);
          siteSelect.appendChild(option);
        });

        siteSelect.disabled = false;
      } catch (error) {
        console.error('خطأ في تحميل المواقع:', error);
        siteSelect.innerHTML = '<option value="0">-- خطأ في التحميل --</option>';
        siteSelect.disabled = true;
      }
    }

    // الاستماع لتغيير الفرع
    branchSelect.addEventListener('change', function() {
      const useAPI = this.getAttribute('data-use-api') === 'true';
      
      if (useAPI) {
        loadSitesFromAPI(this.value);
      } else {
        filterSitesByBranch();
      }
    });

    // تطبيق الفلترة عند التحميل الأولي
    filterSitesByBranch();
  });

})();


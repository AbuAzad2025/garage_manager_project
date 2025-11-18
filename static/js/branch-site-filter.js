(function() {
  'use strict';

  document.addEventListener('DOMContentLoaded', function() {
    const branchSelect = document.getElementById('branch_id');
    const siteSelect = document.getElementById('site_id');
    
    if (!branchSelect || !siteSelect) {
      return; // الحقول غير موجودة في هذه الصفحة
    }

    const allSitesOptions = Array.from(siteSelect.options).map(opt => ({
      value: opt.value,
      text: opt.text,
      branchId: opt.getAttribute('data-branch-id')
    }));

    function filterSitesByBranch() {
      const selectedBranchId = branchSelect.value;
      
      if (!selectedBranchId || selectedLimited === '0' || selectedBranchId === '') {
        repopulateSites(allSitesOptions);
        siteSelect.disabled = true;
        return;
      }

      const filtered = allSitesOptions.filter(opt => {
        return opt.value === '0' || opt.branchId === selectedBranchId;
      });

      repopulateSites(filtered);
      siteSelect.disabled = false;
    }

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

      if (options.some(o => o.value === currentValue)) {
        siteSelect.value = currentValue;
      } else {
        siteSelect.value = '0'; // إعادة تعيين للخيار الافتراضي
      }
    }

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


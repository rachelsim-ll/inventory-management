<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading && recommendations.length === 0" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetLabel') }}</h3>
        </div>
        <div class="budget-controls">
          <input
            type="range"
            class="budget-slider"
            min="0"
            max="50000"
            step="100"
            v-model.number="budget"
            :style="{ '--fill': sliderFillPercent + '%' }"
          />
          <div class="budget-readout">{{ formatCurrency(budget) }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }} ({{ recommendations.length }})</h3>
          <div class="budget-summary">
            <span class="budget-summary-text">
              {{ formatCurrency(totalCost) }} / {{ formatCurrency(budget) }}
            </span>
            <span :class="['badge', isOverBudget ? 'danger' : 'success']">
              {{ isOverBudget ? t('restocking.orderError') : t('restocking.budgetRemaining') }}
            </span>
          </div>
        </div>

        <div v-if="orderSuccessMessage" class="badge success order-banner">
          {{ orderSuccessMessage }}
        </div>

        <div v-if="recommendations.length === 0" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table class="restocking-table">
            <thead>
              <tr>
                <th class="col-sku">{{ t('restocking.table.sku') }}</th>
                <th class="col-name">{{ t('restocking.table.itemName') }}</th>
                <th class="col-warehouse">{{ t('restocking.table.warehouse') }}</th>
                <th class="col-qty">{{ t('restocking.table.currentQty') }}</th>
                <th class="col-qty">{{ t('restocking.table.reorderPoint') }}</th>
                <th class="col-trend">{{ t('restocking.table.trend') }}</th>
                <th class="col-qty">{{ t('restocking.table.recommendedQty') }}</th>
                <th class="col-cost">{{ t('restocking.table.unitCost') }}</th>
                <th class="col-cost">{{ t('restocking.table.lineTotal') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recommendations" :key="item.item_sku">
                <td class="col-sku"><strong>{{ item.item_sku }}</strong></td>
                <td class="col-name">{{ item.item_name }}</td>
                <td class="col-warehouse">{{ item.warehouse }}</td>
                <td class="col-qty">{{ item.current_quantity }}</td>
                <td class="col-qty">{{ item.reorder_point }}</td>
                <td class="col-trend">
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td class="col-qty"><strong>{{ item.recommended_quantity }}</strong></td>
                <td class="col-cost">{{ formatCurrency(item.unit_cost) }}</td>
                <td class="col-cost"><strong>{{ formatCurrency(item.line_total) }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="place-order-row">
          <button
            class="place-order-btn"
            :disabled="recommendations.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.ordering') : t('restocking.placeOrder') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted, watch, computed } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency.js'

export default {
  name: 'Restocking',
  setup() {
    const { t } = useI18n()

    const budget = ref(10000)
    const loading = ref(true)
    const error = ref(null)
    const submitting = ref(false)
    const recommendations = ref([])
    const orderSuccessMessage = ref(null)

    let debounceTimer = null

    // Restocking is filter-independent by design; it intentionally does not use useFilters()
    const loadRecommendations = async () => {
      try {
        loading.value = true
        error.value = null
        recommendations.value = await api.getRestockingRecommendations(budget.value)
      } catch (err) {
        error.value = 'Failed to load restocking recommendations: ' + err.message
      } finally {
        loading.value = false
      }
    }

    watch(budget, () => {
      orderSuccessMessage.value = null
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        loadRecommendations()
      }, 400)
    })

    const totalCost = computed(() => {
      return recommendations.value.reduce((sum, item) => sum + item.line_total, 0)
    })

    const sliderFillPercent = computed(() => (budget.value / 50000) * 100)

    const isOverBudget = computed(() => totalCost.value > budget.value)

    const placeOrder = async () => {
      try {
        submitting.value = true
        error.value = null
        orderSuccessMessage.value = null

        await api.submitRestockingOrder({
          budget: budget.value,
          items: recommendations.value.map(r => ({
            item_sku: r.item_sku,
            item_name: r.item_name,
            quantity: r.recommended_quantity,
            unit_cost: r.unit_cost,
            line_total: r.line_total
          }))
        })

        orderSuccessMessage.value = t('restocking.orderSuccess')
        await loadRecommendations()
      } catch (err) {
        error.value = t('restocking.orderError') + ': ' + err.message
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadRecommendations)

    return {
      t,
      budget,
      loading,
      error,
      submitting,
      recommendations,
      orderSuccessMessage,
      totalCost,
      isOverBudget,
      sliderFillPercent,
      placeOrder,
      formatCurrency
    }
  }
}
</script>

<style scoped>
.budget-controls {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.budget-slider {
  flex: 1;
  -webkit-appearance: none;
  appearance: none;
  height: 6px;
  border-radius: 999px;
  background: linear-gradient(to right, #2563eb 0%, #2563eb var(--fill, 20%), #e2e8f0 var(--fill, 20%), #e2e8f0 100%);
  outline: none;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #2563eb;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.3);
  cursor: pointer;
}

.budget-slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #2563eb;
  border: 2px solid white;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.3);
  cursor: pointer;
}

.budget-slider::-moz-range-track {
  height: 6px;
  border-radius: 999px;
  background: #e2e8f0;
}

.budget-slider::-moz-range-progress {
  height: 6px;
  border-radius: 999px;
  background: #2563eb;
}

.budget-readout {
  min-width: 110px;
  text-align: right;
  font-size: 1.125rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-summary {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.budget-summary-text {
  font-size: 0.875rem;
  font-weight: 600;
  color: #475569;
}

.order-banner {
  display: block;
  margin-bottom: 1rem;
  text-align: center;
  padding: 0.625rem 0.75rem;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

.restocking-table {
  table-layout: fixed;
  width: 100%;
}

.col-sku {
  width: 100px;
}

.col-name {
  width: 200px;
}

.col-warehouse {
  width: 140px;
}

.col-qty {
  width: 110px;
}

.col-trend {
  width: 120px;
}

.col-cost {
  width: 120px;
}

.place-order-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 1rem;
}

.place-order-btn {
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 8px;
  padding: 0.625rem 1.5rem;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}
</style>

import json
import csv
from collections import Counter

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_analysis(base_path, first_path, second_path, first_name, second_name):
    base_data = load_json(base_path)
    first_dict = {item['question_id']: item for item in load_json(first_path)}
    second_dict = {item['question_id']: item for item in load_json(second_path)}
    
    # Filtro rigoroso: solo errori reali
    base_errors = [item for item in base_data if item.get('pred_error') is not None]
    
    first_fixes = Counter()
    second_fixes = Counter()
    residuals = []
    first_fix_ids = []
    second_fix_ids = []
    
    # 1. Primo Step
    for item in base_errors:
        q_id = item['question_id']
        err_type = item.get('pred_error')
        
        if first_dict.get(q_id, {}).get('execution_match') == 1:
            first_fixes[err_type] += 1
            first_fix_ids.append(q_id)
        else:
            if first_dict.get(q_id, {}).get('pred_error') is not None:
                residuals.append(item)

    # 2. Secondo Step (sui residui)
    for item in residuals:
        q_id = item['question_id']
        err_type = item.get('pred_error')
        
        if second_dict.get(q_id, {}).get('execution_match') == 1:
            second_fixes[err_type] += 1
            second_fix_ids.append(q_id)
            
    # 3. Aggregazione per categorie
    summary = {"Ambiguous Column": {"f1": 0, "f2": 0}, "No Such Column": {"f1": 0, "f2": 0}, "Syntax Error": {"f1": 0, "f2": 0}, "Altro": {"f1": 0, "f2": 0}}
    
    all_types = set(first_fixes.keys()) | set(second_fixes.keys())
    for t in all_types:
        t_low = str(t).lower()
        if "ambiguous column" in t_low: cat = "Ambiguous Column"
        elif "no such column" in t_low: cat = "No Such Column"
        elif "syntax error" in t_low: cat = "Syntax Error"
        else: cat = "Altro"
        summary[cat]["f1"] += first_fixes[t]
        summary[cat]["f2"] += second_fixes[t]

    # Stampa Report
    print(f"\n=== Analisi Aggregata: {first_name} -> {second_name} ===")
    print(f"{'Categoria':<20} | {'Risolti 1°':<10} | {'Risolti 2°':<10} | {'Totale':<10}")
    print("-" * 60)
    
    report_rows = []
    t1_sum, t2_sum, tot_sum = 0, 0, 0
    for cat, v in summary.items():
        tot = v["f1"] + v["f2"]
        t1_sum += v["f1"]; t2_sum += v["f2"]; tot_sum += tot
        print(f"{cat:<20} | {v['f1']:<10} | {v['f2']:<10} | {tot:<10}")
        report_rows.append([f"{first_name}->{second_name}", cat, v["f1"], v["f2"], tot])
    
    print("-" * 60)
    print(f"{'RIEPILOGO PASSI':<20} | {t1_sum:<10} | {t2_sum:<10} | {tot_sum:<10}")
    report_rows.append([f"{first_name}->{second_name}", "RIEPILOGO PASSI", t1_sum, t2_sum, tot_sum])
    return report_rows, first_fix_ids, second_fix_ids

def main():

    report_rows_1, description_type_first_fix_ids_1, description_type_second_fix_ids_1 = run_analysis("base.json", "description.json", "type.json", "Description", "Type")
    

    seen= []
    for row in description_type_first_fix_ids_1:
        if row not in seen:
            seen.append(row)
            if row in description_type_second_fix_ids_1:
                print(f"Duplicate in description_type_second_fix_ids_1: {row}")
        else:
            print(f"Duplicate in description_type_first_fix_ids_1: {row}")

    report_rows_2, type_description_first_fix_ids_2, type_description_second_fix_ids_2 = run_analysis("base.json", "type.json", "description.json", "Type", "Description")

    seen_2 = []
    for row in type_description_first_fix_ids_2:
        if row not in seen_2:
            seen_2.append(row)
            if row in type_description_second_fix_ids_2:
                print(f"Duplicate in type_description_second_fix_ids_2: {row}")
        else:
            print(f"Duplicate in type_description_first_fix_ids_2: {row}")


    all_fixed_id_in_first = description_type_first_fix_ids_1 + description_type_second_fix_ids_1 
    print(f"\nTotal  question_ids fixed in first step: {len(all_fixed_id_in_first)}")
    print(f"Total unique question_ids fixed in first step: {len(set(all_fixed_id_in_first))}")

    all_fixed_id_in_second = type_description_first_fix_ids_2 + type_description_second_fix_ids_2
    print(f"\nTotal  question_ids fixed in second step: {len(all_fixed_id_in_second)}")
    print(f"Total unique question_ids fixed in second step: {len(set(all_fixed_id_in_second))}")

    #salvia i risultati in un file json
    with open('2_report_results.json', 'w', encoding='utf-8') as f:
        json.dump({
            "description_type_first_fix_ids_1": description_type_first_fix_ids_1,
            "description_type_second_fix_ids_1": description_type_second_fix_ids_1,
            "type_description_first_fix_ids_2": type_description_first_fix_ids_2,
            "type_description_second_fix_ids_2": type_description_second_fix_ids_2
        }, f, ensure_ascii=False, indent=4)

    



if __name__ == "__main__":
    main()
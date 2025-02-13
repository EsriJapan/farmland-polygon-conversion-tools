#coding:utf-8
#---------------------------------------------------------------------
# Name:       MP_Farmland_ShapefileToFeatureClass.py
# Purpose:    サンプルスクリプト - ArcGIS Pro 環境のマルチプロセスの動作確認用
#               a)農地の筆界シェープファイルを、市区町村FGDB 内のフィーチャクラスに変換（マルチプロセス）
#                 ついでに、自治体コードや自治体名をフィールドに入れる
#               b)市区町村FGDB のフィーチャクラスを、都道府県FGDB 内のフィーチャクラスに統合
#               c)市区町村FGDB の削除
# Author:     Kataya @ ESRI Japan
# Created:    2025/02/10
# Copyright:   (c) ESRI Japan Corporation
# ArcGIS Pro Version:   3.3
# Python Version:   3.9
#---------------------------------------------------------------------
import arcpy,os
import sys
import multiprocessing
import datetime
import traceback
from typing import Tuple,List,Dict

# 
# 補助関数の定義
# 
def __split_citycode_cityname(wsname :str) -> Tuple[str, str]:
    '''
    農地筆のシェープファイルが格納されているフォルダ名から自治体コードと自治体名からそれぞれ抽出して返す関数
    フォルダ名の例）
        02201青森市2019
        02202弘前市2019
    '''
    l = len(wsname)
    citycode = "'{0}'".format(wsname[:5])    #自治体コードだけを抽出
    cityname = '"' + "{0}".format(wsname[5:l-4]) + '"' #自治体名だけを抽出
    return citycode, cityname

# 
# マルチプロセスでの処理関連
# - Python3.3 で追加された pool.starmap は複数の引数に対応しているため、ラッパー関数（ multi_run_batch_convert ）は廃止
# 
def batch_convert(inws :str, outws :str) -> str:
    '''
    1プロセスで実行する処理:
      1) FGDBへの書込みは仕様で複数プロセスで書込みできないため
           1市区町村フォルダ下のシェープファイルを
           1市区町村のFGDB下のフィーチャクラスに変換
      2) 都道府県単位でフィーチャクラスを統合したとき識別しやすいように
           フォルダ名から市区町村コードと、自治体名を作成しフィールドに値を格納
    '''
    #シェープファイルをインポートする市区町村FGDBの作成
    if not arcpy.Exists(outws):
        outfolder = u"{0}".format(os.path.dirname(outws))
        foldername= u"{0}".format(os.path.basename(outws))
        arcpy.management.CreateFileGDB(outfolder, foldername, "CURRENT")
    arcpy.env.workspace = inws
    #自治体コートと自治体名を入れるフィールドを追加で定義
    fieldname1 = "CITYCODE"
    fieldname2 = "CITYNAME"
    fcs = arcpy.ListFeatureClasses()
    for fc in fcs:
        infc = os.path.splitext(fc)[0]
        newfc = u"c_{0}".format(infc) #シェープファイル名が数値ではじまり、FGDBへそのまま変換できないので接頭にc_を入れる
        wsname = os.path.basename(inws)
        citycode, cityname = __split_citycode_cityname(wsname) #フォルダ名から自治体コードと自治体名を抽出
        #座標系はそのままでフィーチャクラスに変換
        if arcpy.Exists(os.path.join(outws, newfc)):
            outfc = os.path.join(outws, newfc)
            arcpy.management.Append(fc, outfc)
        else:
            arcpy.conversion.FeatureClassToFeatureClass(fc, outws, newfc)
            outfc = os.path.join(outws, newfc)
            arcpy.management.AddField(outfc, fieldname1, "TEXT", field_length=5)
            arcpy.management.AddField(outfc, fieldname2, "TEXT", field_length=30)
        # フィールド演算でcitycode, cityname に値をいれる
        calfc = os.path.join(outws, newfc) 
        arcpy.management.CalculateField(calfc, fieldname1, citycode, "PYTHON3", "#")
        arcpy.management.CalculateField(calfc, fieldname2, cityname, "PYTHON3", "#")
    
    del fcs
    return u"  Converted：{0}".format(outws)

def exec_batch_convert(infolder :str, outfolder :str, cpu_cnt :int):
    '''
    マルチプロセスでの処理：
    '''
    try:
        start = datetime.datetime.now()
        arcpy.AddMessage(u"-- Strat: MP_Farmland_ShapefileToFeatureClass --:{0}".format(start))
        
        #a) 各プロセス用の pythonw.exe を設定
        python_path = sys.exec_prefix
        multiprocessing.set_executable(os.path.join(python_path, 'pythonw.exe'))
        #multiprocessing.set_executable(os.path.join(python_path, 'python.exe')) #CMDプロンプトの画面が起動するので'pythonw.exe'を使う
        
        #b) 各プロセスに渡すパラメータをリスト化
        arcpy.AddMessage(u"  Convert each Shapefiles : multiprocessing")
        arcpy.env.workspace = infolder
        inwss = arcpy.ListWorkspaces("*", "Folder")
        params=[]
        for inws in inwss:
            param1 = inws # 市区町村フォルダ（シェープファイルが入っている）
            gdbname = u"{0}.gdb".format(os.path.basename(inws))
            param2 = os.path.join(outfolder, gdbname) # 出力する市区町村ファイルジオデータベース
            params.append((param1, param2))
        if len(inwss) < cpu_cnt: # 処理フォルダ数CPUコアより少ない場合無駄なプロセスを起動不要
            cpu_cnt = len(inwss)
        pool = multiprocessing.Pool(cpu_cnt) # cpu_cnt 数分のプロセスを作成
        results = pool.starmap(batch_convert, params) # 割り当てプロセスで順次実行される（Python3.3で追加されたstarmapは複数の引数に対応）
        pool.close()
        pool.join()
        
        # 各プロセスでの処理結果を出力
        for r in results:
            arcpy.AddMessage(u"{0}".format(r))
        
        #c) 各プロセスで変換された市区町村のフィーチャクラスを都道府県のFGDBへマージしたものを作成（"Farmland"）
        arcpy.env.workspace = outfolder
        outwss = arcpy.ListWorkspaces("*","FileGDB")
        foldername = "{0}.gdb".format(os.path.basename(outfolder))
        fcname = "Farmland" #マージ後のフィーチャクラス名
        arcpy.AddMessage(u"  Mearge to FeatureClass:{1} in FGDB:{0} ".format(foldername, fcname))
        arcpy.management.CreateFileGDB(outfolder, foldername, "CURRENT")
        prefws = os.path.join(outfolder, foldername)
        for outws in outwss:
            arcpy.env.workspace = outws
            fc = arcpy.ListFeatureClasses()[0] #農地筆は1ファイルしかないので固定
            arcpy.AddMessage(u"    merge: {0} ⇒ {1}".format(fc, fcname))
            if arcpy.Exists(os.path.join(prefws, fcname)):
                outfc = os.path.join(prefws, fcname)
                arcpy.management.Append(fc, outfc)
            else:
                arcpy.conversion.FeatureClassToFeatureClass(fc, prefws, fcname)
        
        #d) マージが終わったので後片付け 各市区町村のFGDBを削除
        arcpy.AddMessage(u"  Delete temp FileGDBs")
        for outws in outwss:
            arcpy.AddMessage(u"    Delete FGDB:{0}".format(outws))
            arcpy.management.Delete(outws)
        
        fin = datetime.datetime.now()
        arcpy.AddMessage(u"-- Finish: MP_Farmland_ShapefileToFeatureClass --:{0}".format(fin))
        arcpy.AddMessage(u"     Elapsed time:{0}".format(fin-start))
    except:
        arcpy.AddError(u"Exception:{0}".format(sys.exc_info()[2]))

if __name__ == '__main__':
    '''
    コマンドプロンプトからの実行パラメータを設定の場合：
      infolder: 市区町村別のシェープファイルが入った都道府県フォルダ
      例）
        |-02青森県2019
            |-02201青森市2019
            |   02201青森市2019_5.shp
            |-02202弘前市2019
            |   02202弘前市2019_5.shp
            |-02203八戸市2019
            |-02204黒石市2019	
            ･････
                ※シェープファイルの読み込みの ArcGIS Pro のデフォルトが設定が UTF-8 の場合、*.cpg ファイル（SJIS） をそれぞれに配置しておく必要があります
      
      outfolder: 市区町村別のファイル ジオデータベースの作成先フォルダ
      例)
        |-02青森県2019_filegdb
            |-02201青森市2019.gdb # 市区町村別のFGDBは都道府県にマージ後削除されるようにしている（136行目～）
            |   c_02201青森市2019_5
            |-02202弘前市2019.gdb
            |   c_02202弘前市2019_5
            |-02203八戸市2019
            |-02204黒石市2019	
            ･････
            |-02青森県2019_filegdb.gdb # 市区町村別のフィーチャクラスをマージしたフィーチャクラスを格納するファイル ジオデータベース
            |   Farmland # フィーチャクラス名
      
      cpu_cnt: マルチプロセスでの処理時に起動するプロセス数
    '''
    args = sys.argv
    if len(args) == 4:
        infolder = args[1]
        outfolder = args[2]
        cpu_cnt = int(args[3])
        exec_batch_convert(infolder, outfolder, cpu_cnt)
    else:
        print("Arguments error")
